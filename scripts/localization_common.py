from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


ROOT = Path(__file__).resolve().parents[1]
EN_DIR = ROOT / "input" / "en"
KR_DIR = ROOT / "input" / "kr"
CRES_DIR = ROOT / "input" / "ru-CresCorp"
OUT_DIR = ROOT / "output" / "Limbus-RU-Full"
WORK_DIR = ROOT / "work"
QUEUE_DIR = WORK_DIR / "queues"
GLOSSARY_DIR = WORK_DIR / "glossary"
REPORT_DIR = ROOT / "reports" / "codex"

CYRILLIC_RE = re.compile(r"[А-Яа-яЁёІіЇїЄєҐґ]")
LATIN_RE = re.compile(r"[A-Za-z]")
PLACEHOLDER_RE = re.compile(r"\{[^{}\r\n]+\}")
ANGLE_TAG_NAMES = {
    "i", "b", "u", "s", "size", "color", "sprite", "link", "mark",
    "font", "material", "voffset", "space", "align", "alpha", "br",
    "noparse", "rotate", "cspace", "mspace", "pos", "width", "style",
    "line-height", "indent", "margin", "margin-left", "margin-right",
    "uppercase", "lowercase", "smallcaps", "sub", "sup",
}
ANGLE_TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9-]*)(?:=[^>\r\n]+|\s[^>\r\n]*)?/?>")
BRACKET_TAG_RE = re.compile(r"\[/?[A-Za-z][A-Za-z0-9_]*(?::`[^`\]\r\n]*`)?\]")
BARE_ANGLE_TAG_NAMES = {
    "i", "b", "u", "s", "br", "noparse", "uppercase", "lowercase",
    "smallcaps", "sub", "sup",
}
RESOURCE_RE = re.compile(
    r"^(?:[A-Za-z]:)?[A-Za-z0-9_@.+~\\/:-]+\.(?:json|asset|prefab|png|jpg|jpeg|wav|ogg|mp3|mp4|anim|controller|mat|ttf|otf)$",
    re.IGNORECASE,
)
GUID_RE = re.compile(
    r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{24,64})$",
    re.IGNORECASE,
)
URL_RE = re.compile(r"^(?:https?|ftp)://", re.IGNORECASE)

TECHNICAL_KEYS = {
    "id", "idx", "index", "key", "type", "subtype", "usage",
    "voicefile", "voice_file", "voicekey", "voice_key", "model",
    "prefab", "asset", "assetname", "asset_name", "resource",
    "resourcename", "resource_name", "path", "url", "file",
    "filename", "file_name", "sprite", "icon", "code", "version",
    "hash", "guid", "color", "hex", "language", "locale", "enum",
    "bundle", "address", "addressable", "controller", "animator",
}

IDENTITY_KEYS = (
    "id", "ID", "Id", "idx", "Idx", "key", "Key",
    "personalityid", "personalityId", "personalityID",
    "egoId", "egoID", "egoid", "scenarioId", "scenarioID",
    "scenarioid", "chapterId", "chapterID", "chapterid",
    "stageId", "stageID", "stageid", "episodeId", "episodeID",
)

VISIBLE_KEYS = {
    "content", "contents", "text", "texts", "desc", "description",
    "name", "title", "subtitle", "dlg", "dialog", "dialogue", "message",
    "notice", "label", "caption", "tooltip", "story", "sentence",
    "line", "lyrics", "result", "condition", "effect", "flavor",
    "chapter", "episode", "speaker", "teller", "place", "choice",
}

SPEAKER_KEYS = (
    "speaker", "speakerName", "teller", "tellerName", "character",
    "characterName", "name", "person", "unitName",
)
SCENE_KEYS = (
    "chapterName", "chapter", "episodeName", "episode", "sceneName",
    "scene", "stageName", "title", "subTitle",
)


def ensure_directories() -> None:
    for path in (
        QUEUE_DIR / "ui",
        QUEUE_DIR / "gameplay",
        QUEUE_DIR / "battle_announcers",
        QUEUE_DIR / "personality_voice",
        QUEUE_DIR / "ego_voice",
        QUEUE_DIR / "story",
        QUEUE_DIR / "lyrics",
        QUEUE_DIR / "other",
        GLOSSARY_DIR,
        WORK_DIR / "translations",
        REPORT_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def normalize_filename(name: str) -> str:
    if name.startswith(("EN_", "KR_")):
        return name[3:]
    return name


def normalized_relative_path(path: Path, base: Path) -> Path:
    relative = path.relative_to(base)
    return relative.with_name(normalize_filename(relative.name))


def build_json_index(base: Path) -> tuple[dict[str, Path], list[dict[str, str]]]:
    index: dict[str, Path] = {}
    duplicates: list[dict[str, str]] = []
    for path in sorted(base.rglob("*.json")):
        relative = normalized_relative_path(path, base)
        key = relative.as_posix().casefold()
        if key in index:
            duplicates.append({
                "normalized_path": relative.as_posix(),
                "first": str(index[key]),
                "second": str(path),
            })
            continue
        index[key] = path
    return index, duplicates


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            count += 1
    temporary.replace(path)
    return count


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            count += 1
    return count


def has_cyrillic(value: str) -> bool:
    return bool(CYRILLIC_RE.search(value))


def has_latin(value: str) -> bool:
    return bool(LATIN_RE.search(value))


def scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def object_identity(obj: Any) -> tuple[tuple[str, Any], ...] | None:
    if not isinstance(obj, dict):
        return None
    for key in IDENTITY_KEYS:
        if key in obj and scalar(obj[key]):
            return ((key.casefold(), obj[key]),)
    fields: list[tuple[str, Any]] = []
    for key, value in obj.items():
        lowered = key.casefold()
        if (lowered.endswith("id") or lowered.endswith("_id")) and scalar(value):
            fields.append((lowered, value))
    return tuple(sorted(fields)) if fields else None


def build_identity_map(items: Any) -> dict[tuple[tuple[str, Any], ...], Any] | None:
    if not isinstance(items, list):
        return None
    result: dict[tuple[tuple[str, Any], ...], Any] = {}
    for item in items:
        identity = object_identity(item)
        if identity is None or identity in result:
            return None
        result[identity] = item
    return result


def path_to_text(parts: tuple[Any, ...] | list[Any]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(part)):
            result += f".{part}"
        else:
            result += "[" + json.dumps(str(part), ensure_ascii=False) + "]"
    return result


def get_at_path(value: Any, parts: list[Any] | tuple[Any, ...]) -> Any:
    current = value
    for part in parts:
        current = current[part]
    return current


def set_at_path(value: Any, parts: list[Any] | tuple[Any, ...], replacement: Any) -> None:
    if not parts:
        raise ValueError("Cannot replace the JSON document root")
    parent = get_at_path(value, parts[:-1])
    parent[parts[-1]] = replacement


def extract_placeholders(value: str) -> list[str]:
    return PLACEHOLDER_RE.findall(value)


def is_known_angle_match(match: re.Match[str]) -> bool:
    name = match.group(1).casefold()
    if name not in ANGLE_TAG_NAMES:
        return False
    token = match.group(0)
    if token.startswith("</"):
        return token.casefold() == f"</{name}>"
    if name in BARE_ANGLE_TAG_NAMES:
        return token.casefold() in {f"<{name}>", f"<{name}/>"}
    return True


def extract_tags(value: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for match in ANGLE_TAG_RE.finditer(value):
        if is_known_angle_match(match):
            found.append((match.start(), match.group(0)))
    for match in BRACKET_TAG_RE.finditer(value):
        tag = match.group(0)
        # [Keyword:`visible text`] permits localization of the visible text;
        # only the technical keyword and wrapper must remain identical.
        if ":`" in tag:
            prefix = tag.split(":`", 1)[0]
            tag = prefix + ":`<TEXT>`]"
        found.append((match.start(), tag))
    return [tag for _, tag in sorted(found)]


def is_technical_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.casefold()
    return (
        lowered in TECHNICAL_KEYS
        or lowered.endswith("id")
        or lowered.endswith("_id")
        or lowered.endswith("guid")
        or lowered.endswith("hash")
    )


def visible_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.casefold()
    return lowered in VISIBLE_KEYS or any(
        token in lowered
        for token in ("text", "name", "desc", "title", "content", "dlg", "message", "label", "tooltip")
    )


def technical_reason(value: str, key: Any) -> str | None:
    stripped = value.strip()
    if not stripped:
        return "empty_string"
    if is_technical_key(key):
        return "technical_field"
    if not has_latin(stripped):
        return "no_latin_text"
    without_markup = PLACEHOLDER_RE.sub("", stripped)
    without_markup = BRACKET_TAG_RE.sub("", without_markup)
    without_markup = ANGLE_TAG_RE.sub(
        lambda match: "" if is_known_angle_match(match) else match.group(0),
        without_markup,
    )
    if not has_latin(without_markup):
        return "markup_or_placeholder_only"
    if URL_RE.match(stripped):
        return "url"
    if GUID_RE.fullmatch(stripped):
        return "guid_or_hash"
    if RESOURCE_RE.fullmatch(stripped):
        return "resource_or_filename"
    if not visible_key(key):
        if ("/" in stripped or "\\" in stripped) and " " not in stripped:
            return "path_or_resource_key"
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+", stripped):
            return "internal_snake_case_key"
        if re.fullmatch(r"[A-Z][A-Z0-9_]{1,15}", stripped):
            return "internal_code_or_acronym"
    return None


def category_for(relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/")
    lowered = normalized.casefold()
    filename = Path(normalized).name.casefold()
    if lowered.startswith("storydata/"):
        return "story"
    if lowered.startswith("battleannouncerdlg/"):
        return "battle_announcers"
    if lowered.startswith("personalityvoicedlg/"):
        return "personality_voice"
    if lowered.startswith("egovoicedig/"):
        return "ego_voice"
    if lowered.startswith("bgmlyrics/"):
        return "lyrics"
    is_ui_file = (
        filename.startswith("ui_")
        or "uitext" in filename
        or re.search(r"(?:^|[_-])ui(?:[_-]|\.)", filename) is not None
        or re.search(r"ui(?:text)?(?:[_-]|\.json$)", filename) is not None
    )
    if is_ui_file or any(token in filename for token in ("notice", "message", "caption", "tutorial", "helptext")):
        return "ui"
    if any(token in filename for token in (
        "skill", "passive", "buff", "keyword", "ego", "gift", "battle",
        "personality", "identity", "abnormality", "item", "ability",
        "dungeon", "stage", "enemy", "panic", "attribute", "status",
    )):
        return "gameplay"
    return "other"


def _source_list_item(source: Any, index: int, identity: Any) -> Any:
    if not isinstance(source, list):
        return None
    if identity is not None:
        source_map = build_identity_map(source)
        if source_map is not None:
            return source_map.get(identity)
    return source[index] if index < len(source) else None


def _context_value(obj: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _nearest_context(ancestors: tuple[dict[str, Any], ...], keys: Iterable[str]) -> str | None:
    for obj in reversed(ancestors):
        value = _context_value(obj, keys)
        if value:
            return value
    return None


def _nearest_identity(ancestors: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
    for obj in reversed(ancestors):
        identity = object_identity(obj)
        if identity:
            return {key: value for key, value in identity}
    return None


def _display_preview(value: Any) -> str | None:
    if isinstance(value, str) and value.strip() and not is_technical_key(""):
        return value[:500]
    if isinstance(value, dict):
        priority = ("dlg", "content", "text", "desc", "name", "title", "sentence")
        for key in priority:
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text[:500]
        for key, child in value.items():
            if is_technical_key(key):
                continue
            text = _display_preview(child)
            if text:
                return text
    if isinstance(value, list):
        for child in value[:3]:
            text = _display_preview(child)
            if text:
                return text
    return None


@dataclass
class AlignedLeaf:
    path_parts: tuple[Any, ...]
    key: Any
    output: str
    english: str | None
    korean: str | None
    crescorp: str | None
    object_id: dict[str, Any] | None
    speaker: str | None
    scene: str | None
    neighbors: list[str]


def walk_aligned_strings(
    output: Any,
    english: Any,
    korean: Any = None,
    crescorp: Any = None,
    path: tuple[Any, ...] = (),
    ancestors: tuple[dict[str, Any], ...] = (),
    neighbors: list[str] | None = None,
) -> Iterator[AlignedLeaf]:
    if isinstance(output, str):
        yield AlignedLeaf(
            path_parts=path,
            key=path[-1] if path else "",
            output=output,
            english=english if isinstance(english, str) else None,
            korean=korean if isinstance(korean, str) else None,
            crescorp=crescorp if isinstance(crescorp, str) else None,
            object_id=_nearest_identity(ancestors),
            speaker=_nearest_context(ancestors, SPEAKER_KEYS),
            scene=_nearest_context(ancestors, SCENE_KEYS),
            neighbors=list(neighbors or []),
        )
        return

    if isinstance(output, dict):
        next_ancestors = ancestors + (output,)
        en_dict = english if isinstance(english, dict) else {}
        kr_dict = korean if isinstance(korean, dict) else {}
        cres_dict = crescorp if isinstance(crescorp, dict) else {}
        for key, child in output.items():
            yield from walk_aligned_strings(
                child,
                en_dict.get(key),
                kr_dict.get(key),
                cres_dict.get(key),
                path + (key,),
                next_ancestors,
                neighbors,
            )
        return

    if isinstance(output, list):
        for index, child in enumerate(output):
            identity = object_identity(child)
            en_child = _source_list_item(english, index, identity)
            kr_child = _source_list_item(korean, index, identity)
            cres_child = _source_list_item(crescorp, index, identity)
            adjacent: list[str] = []
            for adjacent_index in (index - 1, index + 1):
                if 0 <= adjacent_index < len(output):
                    preview = _display_preview(output[adjacent_index])
                    if preview:
                        adjacent.append(preview)
            yield from walk_aligned_strings(
                child,
                en_child,
                kr_child,
                cres_child,
                path + (index,),
                ancestors,
                adjacent,
            )


def directory_manifest(base: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    byte_count = 0
    for path in sorted(item for item in base.rglob("*") if item.is_file()):
        relative = path.relative_to(base).as_posix()
        content = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
        file_count += 1
        byte_count += len(content)
    return {
        "path": str(base),
        "files": file_count,
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
    }


def multiset_equal(left: Iterable[str], right: Iterable[str]) -> bool:
    return Counter(left) == Counter(right)


def build_crescorp_baseline(english: Any, crescorp: Any) -> Any:
    """Reproduce the original conservative CresCorp merge without mutating inputs.

    This deliberately stops at array boundaries that cannot be matched either by
    unique stable IDs or by equal-length positional structure. It is the set of
    Russian strings that the generated output is required to preserve verbatim.
    """

    def merge(current: Any, cres: Any) -> Any:
        if isinstance(current, str):
            if isinstance(cres, str) and has_cyrillic(cres):
                return cres
            return current
        if isinstance(current, dict):
            if not isinstance(cres, dict):
                return current
            for key in list(current.keys()):
                if key in cres:
                    current[key] = merge(current[key], cres[key])
            return current
        if isinstance(current, list):
            if not isinstance(cres, list):
                return current
            current_map = build_identity_map(current)
            cres_map = build_identity_map(cres)
            if current_map is not None and cres_map is not None:
                for index, item in enumerate(current):
                    identity = object_identity(item)
                    if identity in cres_map:
                        current[index] = merge(item, cres_map[identity])
                return current
            if len(current) == len(cres):
                for index in range(len(current)):
                    current[index] = merge(current[index], cres[index])
            return current
        return current

    return merge(deepcopy(english), crescorp)
