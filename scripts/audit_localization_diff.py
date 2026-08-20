from __future__ import annotations

"""Recursive, read-only localization audit for Limbus Company JSON trees.

The default code path never mutates the Russian localization.  Reports and an
optional, explicitly requested backup snapshot are written outside ``--ru``.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

try:
    from localization_common import (
        build_json_index,
        category_for,
        extract_placeholders,
        extract_tags,
        has_cyrillic,
        has_latin,
        is_technical_key,
        load_json,
        normalize_filename,
        object_identity,
        path_to_text,
        technical_reason,
        visible_key,
        write_json,
        write_jsonl,
    )
except ImportError:  # pragma: no cover - enables ``python -m unittest``
    from scripts.localization_common import (
        build_json_index,
        category_for,
        extract_placeholders,
        extract_tags,
        has_cyrillic,
        has_latin,
        is_technical_key,
        load_json,
        normalize_filename,
        object_identity,
        path_to_text,
        technical_reason,
        visible_key,
        write_json,
        write_jsonl,
    )


MISSING = object()
HANGUL_RE = re.compile(r"[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]")
WORD_LATIN_RE = re.compile(r"(?<![\w])([A-Za-z][A-Za-z'’.-]{1,})(?![\w])")
MARKUP_PAIR_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9-]*)(?:=[^>]*)?>")
PRECISE_ANGLE_TAG_RE = re.compile(
    r"</?(?:i|b|u|s|size|color|sprite|link|mark|style|nobr|font|material|"
    r"voffset|space|align|alpha|br|noparse|rotate|cspace|mspace|pos|width|"
    r"line-height|indent|margin|margin-left|margin-right|uppercase|lowercase|"
    r"smallcaps|sub|sup)(?:=[^>\r\n]+|\s[^>\r\n]*)?/?>",
    re.IGNORECASE,
)
PRECISE_BRACKET_TAG_RE = re.compile(r"\[/?[A-Za-z][A-Za-z0-9_]*(?::`[^`\]\r\n]*`)?\]")
STRUCTURAL_KINDS = {
    "missing_file",
    "missing_object",
    "missing_field",
    "array_length",
    "type_mismatch",
}

# Exact source literals which are deliberately conventional in Russian builds.
# This is intentionally narrow: additions belong in the generated report and
# must be justified before being promoted here.
CONFIRMED_LITERAL_VALUES = {
    "limbus company",
    "ego",
    "e.g.o",
    "w corp.",
    "r corp.",
    "l corp.",
    "k corp.",
    "t corp.",
    "n corp.",
    "m corp.",
    "p corp.",
    "u corp.",
    "he",
    "teth",
    "waw",
    "zayin",
    "aleph",
    "hp",
    "sp",
    "ui",
    "bgm",
    "ego::",
    "bailemos~",
    "duelo de baile",
    "danza de paz",
    "puñales joviales",
    "flore sicut rosa",
    "cur dolorem sentis",
    "vovete miserias",
    "en un lugar de la mancha",
    "sueño imposible",
    "zàng huā yín",
    "tandem lugetis",
}


def canonical_path(value: str | Path) -> str:
    """Normalize separators and EN_/KR_ prefixes on every path basename."""
    parts = str(value).replace("\\", "/").split("/")
    return "/".join(normalize_filename(part) for part in parts if part not in {"", "."})


def identity_key(value: Any) -> tuple[tuple[str, Any], ...] | None:
    identity = object_identity(value)
    if identity is None:
        return None
    return tuple((str(key).casefold(), scalar) for key, scalar in identity)


def stable_list_map(value: Any) -> dict[tuple[tuple[str, Any], ...], tuple[int, Any]] | None:
    if not isinstance(value, list) or not value:
        return None
    result: dict[tuple[tuple[str, Any], ...], tuple[int, Any]] = {}
    for index, item in enumerate(value):
        identity = identity_key(item)
        if identity is None or identity in result:
            return None
        result[identity] = (index, item)
    return result


def iter_string_semantic_paths(value: Any, semantic: tuple[str, ...] = ()) -> Iterator[tuple[str, ...]]:
    """Yield semantic paths for every string leaf in one localization document."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_string_semantic_paths(child, semantic + (str(key),))
        return
    if isinstance(value, list):
        stable = stable_list_map(value)
        if stable is not None:
            for _, item in stable.values():
                identity = identity_key(item)
                assert identity is not None
                yield from iter_string_semantic_paths(item, semantic + (identity_token(identity),))
            return
        for index, child in enumerate(value):
            child_identity = identity_key(child)
            token = identity_token(child_identity) + f"#{index}" if child_identity else f"#{index}"
            yield from iter_string_semantic_paths(child, semantic + (token,))
        return
    if isinstance(value, str):
        yield semantic


def string_locator_index(root: Path) -> set[tuple[str, tuple[str, ...]]]:
    """Build a lightweight structural string index for a previous RU snapshot."""
    index, _ = build_json_index(root)
    locators: set[tuple[str, tuple[str, ...]]] = set()
    for normalized, path in index.items():
        relative = canonical_path(path.relative_to(root)).casefold()
        for semantic in iter_string_semantic_paths(load_json(path)):
            locators.add((relative, semantic))
    return locators


def identity_dict(value: tuple[tuple[str, Any], ...] | None) -> dict[str, Any] | None:
    return dict(value) if value else None


def identity_token(value: tuple[tuple[str, Any], ...]) -> str:
    return "@" + "+".join(f"{key}={json.dumps(item, ensure_ascii=False, sort_keys=True)}" for key, item in value)


def semantic_locator(relative_path: str, semantic_parts: Iterable[str], field_name: str) -> str:
    return "|".join((canonical_path(relative_path).casefold(), *semantic_parts, field_name.casefold()))


def markup_balanced(value: str) -> bool:
    stack: list[str] = []
    self_closing = {"br", "sprite", "space"}
    for match in MARKUP_PAIR_RE.finditer(value):
        closing, name = match.groups()
        lowered = name.casefold()
        token = match.group(0)
        if token.endswith("/>") or lowered in self_closing or (lowered == "size" and token.casefold() == "<size=0%>"):
            continue
        # Story text often uses literal angle-bracket speech, e.g.
        # ``<Did you <i>really</i> ...?>``.  Unknown phrases are not markup.
        if lowered not in {
            "i", "b", "u", "s", "size", "color", "mark", "style", "nobr",
            "font", "material", "voffset", "align", "alpha", "noparse",
            "uppercase", "lowercase", "smallcaps", "sub", "sup",
        }:
            continue
        if closing:
            if not stack or stack[-1] != lowered:
                return False
            stack.pop()
        else:
            stack.append(lowered)
    return not stack


def audit_tags(value: str) -> list[str]:
    found: list[tuple[int, str]] = []
    known = {
        "i", "b", "u", "s", "size", "color", "sprite", "link", "mark",
        "style", "nobr", "font", "material", "voffset", "space", "align",
        "alpha", "br", "noparse", "rotate", "cspace", "mspace", "pos",
        "width", "line-height", "indent", "margin", "margin-left",
        "margin-right", "uppercase", "lowercase", "smallcaps", "sub", "sup",
    }
    for match in MARKUP_PAIR_RE.finditer(value):
        if match.group(2).casefold() in known:
            found.append((match.start(), match.group(0)))
    for match in re.finditer(r"<sprite\s+name=\"[^\"]+\">", value, re.IGNORECASE):
        found.append((match.start(), match.group(0)))
    for match in PRECISE_BRACKET_TAG_RE.finditer(value):
        tag = match.group(0)
        if ":`" in tag:
            tag = tag.split(":`", 1)[0] + ":`<TEXT>`]"
        found.append((match.start(), tag))
    return [tag for _, tag in sorted(found)]


def required_source_tags(english: str, korean: str | None) -> list[str]:
    """Return formatting tags that a translation must preserve.

    Square-bracketed labels can look exactly like game tags while still being
    localizable display text.  The official Korean localization disambiguates
    them: real game tags keep the same ASCII identifier (for example
    ``[Combustion]``), whereas labels such as ``[Chachihu]`` are translated.
    When Korean context is unavailable, keep the conservative legacy behavior
    and require every English bracket tag.
    """

    english_tags = audit_tags(english)
    if not korean:
        return english_tags
    korean_tags = Counter(audit_tags(korean))
    localized_bracket_slots = sum(
        1
        for match in re.finditer(r"\[[^\]\r\n]+\]", korean)
        if PRECISE_BRACKET_TAG_RE.fullmatch(match.group(0)) is None
    )
    required: list[str] = []
    for tag in english_tags:
        if tag.startswith("["):
            if korean_tags[tag] > 0:
                korean_tags[tag] -= 1
            elif localized_bracket_slots > 0:
                localized_bracket_slots -= 1
                continue
        required.append(tag)
    return required


def intentional_literal_reason(value: str, key: Any) -> str | None:
    stripped = value.strip()
    technical = technical_reason(stripped, key)
    if technical:
        return technical
    lowered = stripped.casefold()
    if lowered in CONFIRMED_LITERAL_VALUES:
        return "confirmed_game_literal"
    if HANGUL_RE.search(stripped):
        return "source_internal_korean_comment"
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}", stripped):
        return "technical_color_literal"
    if re.fullmatch(r"DN-\d{5}", stripped, re.IGNORECASE):
        return "internal_node_code"
    if isinstance(key, str) and key.casefold() in {"keywords", "keyword", "songwriter", "composer", "artist", "singer"}:
        return "technical_keyword_or_credit"
    if re.fullmatch(r"[A-Z]{2,6}\??", stripped):
        return "acronym_or_rank_literal"
    if re.fullmatch(r"[A-Z]{2,6}[!?]?", stripped):
        return "acronym_or_rank_literal"
    if re.fullmatch(r"[A-Z]?`?-[A-Za-z0-9`]+(?:-[A-Za-z0-9]+){2,6}", stripped, re.IGNORECASE):
        return "abnormality_or_internal_code"
    if re.fullmatch(r"\d{5,}[A-Za-z]?", stripped):
        return "internal_numeric_code"
    if re.fullmatch(r"(?:XX/XX|MM/dd)", stripped):
        return "date_format_literal"
    if stripped.startswith("[DEVELOPER COMMENT"):
        return "developer_comment"
    if re.fullmatch(r"<…[A-Z]{2,6}\?>", stripped):
        return "stylized_acronym_literal"
    if re.fullmatch(r"<style=\"den[^\"]*\">[^<]+</style>", stripped, re.IGNORECASE):
        return "original_lyric_literal"
    if stripped and sum(character.isalnum() for character in stripped) / len(stripped) < 0.35:
        return "symbolic_or_obfuscated_literal"
    if re.fullmatch(r"[IVXLCDM]+", stripped):
        return "roman_numeral"
    if re.fullmatch(r"[A-Z](?:\.[A-Z])+\.?", stripped):
        return "initialism"
    if re.fullmatch(r"\s*[A-Z]{1,3}(?:-[A-Za-z0-9]{1,4}){2,6}\s*", stripped, re.IGNORECASE):
        return "abnormality_or_internal_code"
    return None


def is_visible_source(value: Any, key: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or is_technical_key(key):
        return False
    return technical_reason(value, key) is None


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detailed_manifest(base: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    aggregate = hashlib.sha256()
    byte_count = 0
    for path in sorted(item for item in base.rglob("*") if item.is_file()):
        relative = path.relative_to(base).as_posix()
        size = path.stat().st_size
        digest = hash_file(path)
        files.append({"path": relative, "bytes": size, "sha256": digest})
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(bytes.fromhex(digest))
        byte_count += size
    return {
        "root": str(base.resolve()),
        "file_count": len(files),
        "bytes": byte_count,
        "sha256": aggregate.hexdigest(),
        "files": files,
    }


def create_snapshot(
    en: Path,
    kr: Path,
    ru: Path,
    snapshot_dir: Path,
    target_version: str,
) -> Path:
    """Create a one-time byte-for-byte output backup plus hash manifests."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    backup_root = snapshot_dir / "baseline_output"
    manifest_path = snapshot_dir / "backup_manifest.json"
    if backup_root.exists() or manifest_path.exists():
        raise FileExistsError(
            f"Snapshot target already exists: {snapshot_dir}. Refusing to overwrite it."
        )
    shutil.copytree(ru, backup_root, copy_function=shutil.copy2)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target_version": target_version,
        "purpose": f"pre-{target_version} localization backup",
        "input_en": detailed_manifest(en),
        "input_kr": detailed_manifest(kr),
        "output_ru_before_update": detailed_manifest(ru),
        "backup_output": detailed_manifest(backup_root),
    }
    if manifest["output_ru_before_update"]["sha256"] != manifest["backup_output"]["sha256"]:
        raise RuntimeError("Output backup verification failed")
    write_json(manifest_path, manifest)
    return manifest_path


def frozen(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def baseline_candidates(path: Path | None) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    """Load only compact source-change fields from the large previous index."""
    result: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    if path is None or not path.exists():
        return result
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            relative = canonical_path(row.get("normalized_file", "")).casefold()
            field_name = str(row.get("field", "")).casefold()
            stable_id = frozen(row.get("stable_id") or {})
            compact = {
                "previous_english": row.get("new_english_value", row.get("previous_english_value")),
                "previous_korean": row.get("new_korean_value", row.get("previous_korean_value")),
                "previous_russian": row.get("current_russian_value"),
                "json_path": row.get("output_json_path") or row.get("json_path"),
                "semantic_path": row.get("semantic_path"),
                "composite_key": row.get("composite_key"),
            }
            result[(relative, stable_id, field_name)].append(compact)
            semantic_path = compact.get("semantic_path")
            if semantic_path:
                result[(relative, "__SEMANTIC__", frozen(semantic_path))].append(compact)
            json_path = compact.get("json_path")
            if json_path:
                result[(relative, "__PATH__", str(json_path))].append(compact)
    return result


def prior_queue_index(path: Path | None) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    if path is None or not path.exists():
        return result
    files = [path] if path.is_file() else sorted(path.rglob("*.jsonl"))
    for queue_file in files:
        with queue_file.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                relative = canonical_path(row.get("relative_path", row.get("normalized_file", ""))).casefold()
                stable = frozen(row.get("stable_id") or {})
                field_name = str(row.get("field") or (row.get("path_parts") or [""])[-1]).casefold()
                english = frozen(row.get("english", row.get("new_english_value")))
                result[(relative, stable, field_name, english)] = {
                    "status": row.get("status"),
                    "translation": row.get("translation"),
                    "queue_id": row.get("queue_id"),
                }
    return result


def load_review_decisions(path: Path) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return decisions
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            queue_id = row.get("queue_id")
            status = row.get("status")
            if not isinstance(queue_id, str) or status not in {"reviewed", "intentional"}:
                raise ValueError(f"{path}:{line_number}: invalid review decision")
            decisions[queue_id] = row
    return decisions


def review_scope_index(path: Path | None) -> tuple[set[tuple[str, str, str]], set[tuple[str, str, str]]]:
    """Index the project's previously translated full queues.

    A previous source index normally lives below ``work/updates``; its sibling
    ``work/queues`` is the accepted full-review corpus.  The lookup is
    deliberately version-agnostic so the same command can be reused for every
    game update.
    """
    locator_counts: Counter[tuple[str, str, str]] = Counter()
    paths: set[tuple[str, str, str]] = set()
    if path is None:
        return set(), paths
    work_root = path.resolve().parents[2] if len(path.resolve().parents) >= 3 else None
    queue_root = work_root / "queues" if work_root else None
    if queue_root is None or not queue_root.exists():
        return set(), paths
    for queue_file in sorted(queue_root.rglob("*.jsonl")):
        with queue_file.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                relative = canonical_path(row.get("relative_path", "")).casefold()
                stable = frozen(row.get("stable_id") or row.get("object_id") or {})
                field_name = str(row.get("field") or (row.get("path_parts") or [""])[-1]).casefold()
                locator_counts[(relative, stable, field_name)] += 1
                if row.get("json_path"):
                    paths.add((relative, row["json_path"], frozen(row.get("english"))))
    return {locator for locator, count in locator_counts.items() if count == 1}, paths


def choose_baseline(
    candidates: dict[tuple[str, str, str], list[dict[str, Any]]],
    relative: str,
    stable_id: dict[str, Any] | None,
    field_name: str,
    english: Any,
    json_path: str,
    semantic_path: tuple[str, ...],
) -> dict[str, Any] | None:
    normalized = canonical_path(relative).casefold()
    rows = candidates.get((normalized, frozen(stable_id or {}), field_name.casefold()), [])
    exact_source = [row for row in rows if row.get("previous_english") == english]
    if len(exact_source) == 1:
        return exact_source[0]
    semantic_rows = candidates.get((normalized, "__SEMANTIC__", frozen(semantic_path)), [])
    if len(semantic_rows) == 1:
        return semantic_rows[0]
    exact_path = [row for row in rows if row.get("json_path") == json_path]
    if len(exact_path) == 1:
        return exact_path[0]
    path_rows = candidates.get((normalized, "__PATH__", json_path), [])
    if len(path_rows) == 1:
        return path_rows[0]
    return None


@dataclass
class AuditState:
    missing_structure: list[dict[str, Any]] = field(default_factory=list)
    changed_source: list[dict[str, Any]] = field(default_factory=list)
    untranslated: list[dict[str, Any]] = field(default_factory=list)
    latin_review: list[dict[str, Any]] = field(default_factory=list)
    intentional_literals: list[dict[str, Any]] = field(default_factory=list)
    full_review: list[dict[str, Any]] = field(default_factory=list)
    technical_mismatches: list[dict[str, Any]] = field(default_factory=list)
    format_errors: list[dict[str, Any]] = field(default_factory=list)
    positional_arrays: list[dict[str, Any]] = field(default_factory=list)
    source_index: list[dict[str, Any]] = field(default_factory=list)


class Auditor:
    def __init__(
        self,
        baseline: dict[tuple[str, str, str], list[dict[str, Any]]],
        prior: dict[tuple[str, str, str, str], dict[str, Any]],
        review_scope: tuple[set[tuple[str, str, str]], set[tuple[str, str, str]]] | None = None,
        update_files: set[str] | None = None,
        decisions: dict[str, dict[str, Any]] | None = None,
        full_review: bool = False,
        previous_output_locators: set[tuple[str, tuple[str, ...]]] | None = None,
    ) -> None:
        self.baseline = baseline
        self.prior = prior
        self.review_scope = review_scope or (set(), set())
        self.update_files = update_files
        self.decisions = decisions or {}
        self.full_review = full_review
        self.previous_output_locators = previous_output_locators
        self.state = AuditState()

    def _issue(self, collection: list[dict[str, Any]], relative: str, path: tuple[Any, ...], kind: str, **extra: Any) -> None:
        collection.append({
            "relative_path": relative,
            "json_path": path_to_text(path),
            "kind": kind,
            **extra,
        })

    def _missing(self, relative: str, path: tuple[Any, ...], kind: str, **extra: Any) -> None:
        self._issue(self.state.missing_structure, relative, path, kind, **extra)

    def compare_file(self, relative: str, english: Any, korean: Any, russian: Any) -> None:
        self._walk(relative, english, korean, russian, (), (), (), (), None)

    def _walk(
        self,
        relative: str,
        english: Any,
        korean: Any,
        russian: Any,
        path: tuple[Any, ...],
        semantic: tuple[str, ...],
        identities: tuple[dict[str, Any], ...],
        neighbors: tuple[str, ...],
        key: Any,
    ) -> None:
        if russian is MISSING:
            # The parent-level structural issue is sufficient; still descend so
            # every new visible source leaf enters the translation queue.
            pass
        elif type(english) is not type(russian):
            self._missing(
                relative,
                path,
                "type_mismatch",
                english_type=type(english).__name__,
                russian_type=type(russian).__name__,
            )
            if isinstance(english, str):
                self._visible_leaf(relative, english, korean, russian, path, semantic, identities, neighbors, key)
            return

        if isinstance(english, dict):
            ru_dict = russian if isinstance(russian, dict) else {}
            kr_dict = korean if isinstance(korean, dict) else {}
            for child_key, en_child in english.items():
                if child_key not in ru_dict and russian is not MISSING:
                    self._missing(relative, path + (child_key,), "missing_field", field=child_key)
                self._walk(
                    relative,
                    en_child,
                    kr_dict.get(child_key, MISSING),
                    ru_dict.get(child_key, MISSING),
                    path + (child_key,),
                    semantic + (str(child_key),),
                    identities,
                    neighbors,
                    child_key,
                )
            return

        if isinstance(english, list):
            kr_list = korean if isinstance(korean, list) else []
            ru_list = russian if isinstance(russian, list) else []
            en_map = stable_list_map(english)
            ru_map = stable_list_map(ru_list)
            kr_map = stable_list_map(kr_list)
            if en_map is not None:
                if russian is not MISSING and len(english) != len(ru_list):
                    self._missing(relative, path, "array_length", english_length=len(english), russian_length=len(ru_list), alignment="stable_id")
                for en_index, item in enumerate(english):
                    identity = identity_key(item)
                    assert identity is not None
                    ru_entry = ru_map.get(identity) if ru_map is not None else None
                    kr_entry = kr_map.get(identity) if kr_map is not None else None
                    if ru_entry is None and russian is not MISSING:
                        self._missing(relative, path + (en_index,), "missing_object", stable_id=identity_dict(identity))
                    ru_index, ru_child = ru_entry if ru_entry is not None else (en_index, MISSING)
                    _, kr_child = kr_entry if kr_entry is not None else (en_index, MISSING)
                    adjacent = self._neighbors(ru_list if ru_list else english, ru_index)
                    self._walk(
                        relative,
                        item,
                        kr_child,
                        ru_child,
                        path + (ru_index,),
                        semantic + (identity_token(identity),),
                        identities + (identity_dict(identity) or {},),
                        adjacent,
                        key,
                    )
                return

            if english and not all(not isinstance(item, (dict, list)) for item in english):
                self.state.positional_arrays.append({
                    "relative_path": relative,
                    "json_path": path_to_text(path),
                    "english_length": len(english),
                    "russian_length": len(ru_list),
                    "reason": "no_unique_stable_identity",
                })
            if russian is not MISSING and len(english) != len(ru_list):
                self._missing(relative, path, "array_length", english_length=len(english), russian_length=len(ru_list), alignment="positional")
            for index, en_child in enumerate(english):
                kr_child = kr_list[index] if index < len(kr_list) else MISSING
                ru_child = ru_list[index] if index < len(ru_list) else MISSING
                child_identity = identity_key(en_child)
                child_identities = identities + ((identity_dict(child_identity) or {}),) if child_identity else identities
                semantic_token = identity_token(child_identity) + f"#{index}" if child_identity else f"#{index}"
                self._walk(
                    relative,
                    en_child,
                    kr_child,
                    ru_child,
                    path + (index,),
                    semantic + (semantic_token,),
                    child_identities,
                    self._neighbors(ru_list if ru_list else english, index),
                    key,
                )
            return

        if isinstance(english, str):
            self._visible_leaf(relative, english, korean, russian, path, semantic, identities, neighbors, key)
            return

        if russian is not MISSING and english != russian:
            self._issue(
                self.state.technical_mismatches,
                relative,
                path,
                "technical_value_mismatch",
                english=english,
                russian=russian,
            )

    @staticmethod
    def _neighbors(items: list[Any], index: int) -> tuple[str, ...]:
        result: list[str] = []
        for neighbor_index in (index - 1, index + 1):
            if not 0 <= neighbor_index < len(items):
                continue
            item = items[neighbor_index]
            if isinstance(item, dict):
                for candidate in ("dialog", "dlg", "content", "desc", "name", "title", "text"):
                    value = item.get(candidate)
                    if isinstance(value, str) and value.strip():
                        result.append(value[:500])
                        break
            elif isinstance(item, str) and item.strip():
                result.append(item[:500])
        return tuple(result)

    def _visible_leaf(
        self,
        relative: str,
        english: str,
        korean: Any,
        russian: Any,
        path: tuple[Any, ...],
        semantic: tuple[str, ...],
        identities: tuple[dict[str, Any], ...],
        neighbors: tuple[str, ...],
        key: Any,
    ) -> None:
        stable_id = identities[-1] if identities else None
        json_path = path_to_text(path)
        queue_id = hashlib.sha1((semantic_locator(relative, semantic, str(key)) + "\0" + english).encode("utf-8")).hexdigest()[:20]
        scope_locator = (canonical_path(relative).casefold(), frozen(stable_id or {}), str(key).casefold())
        in_prior_review_scope = (
            scope_locator in self.review_scope[0]
            or (canonical_path(relative).casefold(), json_path, frozen(english)) in self.review_scope[1]
        )
        baseline = choose_baseline(
            self.baseline,
            relative,
            stable_id,
            str(key),
            english,
            json_path,
            semantic,
        )
        source_changed_at_leaf = baseline is not None and baseline.get("previous_english") != english
        previous_english = baseline.get("previous_english") if baseline else None
        source_change_type = "NEW_SOURCE_LEAF" if baseline is None else ("CHANGED_SOURCE" if source_changed_at_leaf else "UNCHANGED")
        ru_value = russian if isinstance(russian, str) else None
        kr_value = korean if isinstance(korean, str) else None
        source_row = {
            "normalized_file": canonical_path(relative),
            "stable_id": stable_id,
            "parent_ids": list(identities),
            "field": key,
            "json_path": json_path,
            "semantic_path": list(semantic),
            "new_english_value": english,
            "new_korean_value": kr_value,
            "current_russian_value": ru_value,
            "source_change_type": source_change_type,
            "review_status": "not_in_review_scope",
        }
        self.state.source_index.append(source_row)
        new_visible_source = is_visible_source(english, key)
        missing_or_copied_source = russian is MISSING or russian == english
        is_new_output_leaf = (
            self.previous_output_locators is not None
            and (canonical_path(relative).casefold(), semantic) not in self.previous_output_locators
        )
        has_recorded_decision = queue_id in self.decisions
        in_scope = (
            in_prior_review_scope
            or source_changed_at_leaf
            or (new_visible_source and (missing_or_copied_source or is_new_output_leaf))
            or has_recorded_decision
            if self.full_review
            else (
                source_changed_at_leaf
                or (new_visible_source and (missing_or_copied_source or is_new_output_leaf))
                or has_recorded_decision
            )
        )
        if not in_scope:
            if russian is not MISSING and english != russian and is_technical_key(key):
                self._issue(
                    self.state.technical_mismatches,
                    relative,
                    path,
                    "technical_string_mismatch",
                    english=english,
                    russian=russian,
                    field=key,
                )
            return

        source_changed = source_changed_at_leaf

        placeholder_error = ru_value is not None and Counter(extract_placeholders(english)) != Counter(extract_placeholders(ru_value))
        source_tags = required_source_tags(english, kr_value)
        tag_error = ru_value is not None and Counter(source_tags) != Counter(audit_tags(ru_value))
        markup_error = ru_value is not None and markup_balanced(english) and not markup_balanced(ru_value)
        hangul_error = bool(ru_value and HANGUL_RE.search(ru_value) and not (ru_value == english and kr_value == english))
        exact_english = ru_value == english
        literal_reason = intentional_literal_reason(english, key) if exact_english else None
        legacy_tag_expansion = bool(
            tag_error
            and baseline
            and not source_changed
            and (
                ru_value == baseline.get("previous_russian")
                or ru_value.replace("</nobr>", "<nobr>") == baseline.get("previous_russian")
            )
        )
        effective_tag_error = tag_error and not legacy_tag_expansion

        if ru_value is None:
            status, reason = "pending", "missing_russian_value"
        elif placeholder_error or effective_tag_error or markup_error or hangul_error:
            status, reason = "pending", "format_or_source_residue_error"
        elif exact_english and literal_reason is None:
            status, reason = "pending", "exact_english_match"
        elif exact_english:
            status, reason = "intentional", literal_reason
        elif source_changed and baseline and ru_value == baseline.get("previous_russian"):
            status, reason = "pending", "source_changed_russian_unchanged"
        elif legacy_tag_expansion:
            status, reason = "reviewed", "legacy_expanded_game_tags_reviewed"
        else:
            status, reason = "reviewed", "translated_and_static_checks_passed"

        prior = self.prior.get((
            canonical_path(relative).casefold(),
            frozen(stable_id or {}),
            str(key).casefold(),
            frozen(english),
        ))
        if prior and prior.get("status") == "intentional" and exact_english and status == "pending":
            status, reason = "intentional", "confirmed_by_prior_queue"

        decision = self.decisions.get(queue_id)
        if decision:
            status = decision["status"]
            reason = decision.get("reason", "recorded_review_decision")
        source_row["review_status"] = status
        row = {
            "queue_id": queue_id,
            "relative_path": canonical_path(relative),
            "json_path": json_path,
            "path_parts": list(path),
            "semantic_path": list(semantic),
            "stable_id": stable_id,
            "parent_ids": list(identities),
            "field": key,
            "english": english,
            "korean": kr_value,
            "current_russian": ru_value,
            "neighbors": list(neighbors),
            "category": category_for(relative),
            "status": status,
            "review_reason": reason,
            "source_change_type": source_change_type,
            "previous_english": previous_english,
            "previous_russian": baseline.get("previous_russian") if baseline else None,
            "placeholders": extract_placeholders(english),
            "game_tags": source_tags,
            "placeholder_mismatch": placeholder_error,
            "tag_mismatch": tag_error,
            "legacy_tag_expansion": legacy_tag_expansion,
            "markup_unbalanced": markup_error,
            "hangul_residue": hangul_error,
        }
        self.state.full_review.append(row)
        if source_changed:
            self.state.changed_source.append(row)
        if ru_value is None or exact_english:
            if status == "intentional":
                self.state.intentional_literals.append({**row, "intentional_reason": reason})
            else:
                self.state.untranslated.append(row)
        if ru_value and has_latin(ru_value):
            visible_words = sorted(set(WORD_LATIN_RE.findall(ru_value)))
            if visible_words:
                self.state.latin_review.append({**row, "latin_words": visible_words})
        if placeholder_error or effective_tag_error or markup_error or hangul_error:
            self.state.format_errors.append(row)


def write_summary(report_dir: Path, summary: dict[str, Any]) -> None:
    write_json(report_dir / "summary.json", summary)
    counts = summary["counts"]
    lines = [
        f"# Аудит локализации {summary['target_version']}",
        "",
        f"Сформирован: `{summary['generated_at']}`",
        "",
        "## Итог",
        "",
        f"- EN / KR / RU файлов: **{counts['english_files']} / {counts['korean_files']} / {counts['russian_files']}**",
        f"- Видимых строк: **{counts['visible_strings']}**",
        f"- reviewed / intentional / pending: **{counts['reviewed']} / {counts['intentional']} / {counts['pending']}**",
        f"- Пропуски структуры: **{counts['missing_structure']}**",
        f"- Изменившийся оригинал: **{counts['changed_source']}**",
        f"- Точные совпадения с английским без исключения: **{counts['untranslated']}**",
        f"- Отсутствующий русский текст: **{counts['missing_russian_text']}**",
        f"- Русский текст, совпадающий с английским: **{counts['exact_english_text']}**",
        f"- Ошибки плейсхолдеров, тегов, разметки или корейские остатки: **{counts['format_errors']}**",
        f"- Несовпадения технических значений: **{counts['technical_mismatches']}**",
        f"- Массивы с позиционным сопоставлением: **{counts['positional_arrays']}**",
        f"- Строк в полном индексе источника: **{counts['source_strings_indexed']}**",
        "",
        "## Парность",
        "",
        f"- EN без KR: **{counts['english_without_korean']}**",
        f"- KR без EN: **{counts['korean_without_english']}**",
        f"- EN без RU: **{counts['english_without_russian']}**",
        f"- RU без EN: **{counts['russian_without_english']}**",
        "",
        f"Обязательных блокеров для `--check`: **{summary['blocking_count']}**.",
        "",
    ]
    (report_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def audit(args: argparse.Namespace) -> dict[str, Any]:
    en_root = args.en.resolve()
    kr_root = args.kr.resolve()
    ru_root = args.ru.resolve()
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    if args.snapshot_dir:
        create_snapshot(
            en_root,
            kr_root,
            ru_root,
            args.snapshot_dir.resolve(),
            args.target_version,
        )

    en_index, en_duplicates = build_json_index(en_root)
    kr_index, kr_duplicates = build_json_index(kr_root)
    ru_index, ru_duplicates = build_json_index(ru_root)
    baseline = baseline_candidates(args.baseline_index)
    prior = prior_queue_index(args.prior_queues)
    review_scope = review_scope_index(args.baseline_index)
    decisions = load_review_decisions(report_dir / "review_decisions.jsonl")
    update_files: set[str] | None = None
    previous_output_locators: set[tuple[str, tuple[str, ...]]] | None = None
    if args.baseline_index:
        work_root = args.baseline_index.resolve().parents[2]
        snapshot_root = work_root / "updates" / report_dir.name / "baseline_output"
        if snapshot_root.exists():
            previous_output_locators = string_locator_index(snapshot_root)
            snapshot_index, _ = build_json_index(snapshot_root)
            update_files = set()
            for normalized, ru_path in ru_index.items():
                snapshot_path = snapshot_index.get(normalized)
                if snapshot_path is None or hash_file(snapshot_path) != hash_file(ru_path):
                    update_files.add(normalized)
    auditor = Auditor(
        baseline,
        prior,
        review_scope,
        update_files,
        decisions,
        full_review=args.mode == "full-review",
        previous_output_locators=previous_output_locators,
    )

    en_keys, kr_keys, ru_keys = set(en_index), set(kr_index), set(ru_index)
    for key in sorted(en_keys):
        relative = canonical_path(en_index[key].relative_to(en_root))
        english = load_json(en_index[key])
        korean = load_json(kr_index[key]) if key in kr_index else MISSING
        if key not in ru_index:
            auditor._missing(relative, (), "missing_file", english_file=str(en_index[key]))
            russian = MISSING
        else:
            russian = load_json(ru_index[key])
        auditor.compare_file(relative, english, korean, russian)

    state = auditor.state
    report_files = {
        "missing_structure.jsonl": state.missing_structure,
        "changed_source.jsonl": state.changed_source,
        "untranslated.jsonl": state.untranslated,
        "latin_review.jsonl": state.latin_review,
        "intentional_literals.jsonl": state.intentional_literals,
        "technical_mismatches.jsonl": state.technical_mismatches,
        "format_errors.jsonl": state.format_errors,
        "positional_arrays.jsonl": state.positional_arrays,
        "source_index.jsonl": state.source_index,
    }
    for name, rows in report_files.items():
        write_jsonl(report_dir / name, rows)

    queue_root = report_dir / "queues"
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in state.full_review:
        grouped[row["category"]].append(row)
    for category, rows in sorted(grouped.items()):
        write_jsonl(queue_root / f"{category}.jsonl", rows)

    statuses = Counter(row["status"] for row in state.full_review)
    missing_russian_text = sum(row["current_russian"] is None for row in state.untranslated)
    exact_english_text = sum(row["current_russian"] == row["english"] for row in state.untranslated)
    pairing = {
        "english_without_korean": sorted(canonical_path(en_index[key].relative_to(en_root)) for key in en_keys - kr_keys),
        "korean_without_english": sorted(canonical_path(kr_index[key].relative_to(kr_root)) for key in kr_keys - en_keys),
        "english_without_russian": sorted(canonical_path(en_index[key].relative_to(en_root)) for key in en_keys - ru_keys),
        "russian_without_english": sorted(canonical_path(ru_index[key].relative_to(ru_root)) for key in ru_keys - en_keys),
    }
    write_json(report_dir / "file_pairing.json", pairing)

    blocking_count = (
        len(state.missing_structure)
        + statuses.get("pending", 0)
        + len(state.technical_mismatches)
    )
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_version": args.target_version,
        "mode": args.mode,
        "roots": {"en": str(en_root), "kr": str(kr_root), "ru": str(ru_root)},
        "counts": {
            "english_files": len(en_index),
            "korean_files": len(kr_index),
            "russian_files": len(ru_index),
            "visible_strings": len(state.full_review),
            "reviewed": statuses.get("reviewed", 0),
            "intentional": statuses.get("intentional", 0),
            "pending": statuses.get("pending", 0),
            "missing_structure": len(state.missing_structure),
            "changed_source": len(state.changed_source),
            "untranslated": len(state.untranslated),
            "missing_russian_text": missing_russian_text,
            "exact_english_text": exact_english_text,
            "latin_review": len(state.latin_review),
            "intentional_literals": len(state.intentional_literals),
            "format_errors": len(state.format_errors),
            "technical_mismatches": len(state.technical_mismatches),
            "positional_arrays": len(state.positional_arrays),
            "source_strings_indexed": len(state.source_index),
            "english_without_korean": len(pairing["english_without_korean"]),
            "korean_without_english": len(pairing["korean_without_english"]),
            "english_without_russian": len(pairing["english_without_russian"]),
            "russian_without_english": len(pairing["russian_without_english"]),
            "duplicate_english_paths": len(en_duplicates),
            "duplicate_korean_paths": len(kr_duplicates),
            "duplicate_russian_paths": len(ru_duplicates),
        },
        "blocking_count": blocking_count,
        "report_files": sorted(report_files),
    }
    write_summary(report_dir, summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--en", type=Path, required=True)
    parser.add_argument("--kr", type=Path, required=True)
    parser.add_argument("--ru", type=Path, required=True)
    parser.add_argument(
        "--target-version",
        required=True,
        help="Version label recorded in snapshots and reports (for example 1.112.0-post-2026-08-20)",
    )
    parser.add_argument("--baseline-index", type=Path)
    parser.add_argument("--prior-queues", type=Path)
    parser.add_argument("--mode", choices=("diff", "full-review"), default="diff")
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, help="Create a verified one-time output backup before auditing")
    parser.add_argument("--check", action="store_true", help="Exit non-zero while mandatory findings remain")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = audit(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if args.check and summary["blocking_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
