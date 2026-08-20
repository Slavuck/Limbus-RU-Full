from __future__ import annotations

"""Synchronize Russian JSON structure with English without translating text."""

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    from audit_localization_diff import canonical_path, detailed_manifest, identity_key, stable_list_map
    from localization_common import build_json_index, is_technical_key, load_json, write_json
except ImportError:  # pragma: no cover
    from scripts.audit_localization_diff import canonical_path, detailed_manifest, identity_key, stable_list_map
    from scripts.localization_common import build_json_index, is_technical_key, load_json, write_json


def merge_structure(english: Any, russian: Any, key: Any = None) -> Any:
    """Return EN-shaped data while preserving aligned Russian visible strings."""
    if isinstance(english, dict):
        ru_dict = russian if isinstance(russian, dict) else {}
        return {
            child_key: merge_structure(child, ru_dict.get(child_key), child_key)
            if child_key in ru_dict
            else deepcopy(child)
            for child_key, child in english.items()
        }
    if isinstance(english, list):
        ru_list = russian if isinstance(russian, list) else []
        en_map = stable_list_map(english)
        ru_map = stable_list_map(ru_list)
        if en_map is not None and ru_map is not None:
            merged: list[Any] = []
            for _, en_item in en_map.values():
                identity = identity_key(en_item)
                ru_entry = ru_map.get(identity) if identity is not None else None
                merged.append(merge_structure(en_item, ru_entry[1]) if ru_entry else deepcopy(en_item))
            return merged
        return [
            merge_structure(item, ru_list[index]) if index < len(ru_list) else deepcopy(item)
            for index, item in enumerate(english)
        ]
    if isinstance(english, str):
        if is_technical_key(key):
            return english
        return russian if isinstance(russian, str) else english
    return deepcopy(english)


def verified_backup(manifest_path: Path, ru_root: Path) -> None:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Required backup manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    backup = manifest_path.parent / "baseline_output"
    if not backup.exists():
        raise FileNotFoundError(f"Required backup tree not found: {backup}")
    expected = manifest["backup_output"]["sha256"]
    actual = detailed_manifest(backup)["sha256"]
    if actual != expected:
        raise RuntimeError("Backup tree no longer matches its manifest")
    if Path(manifest["output_ru_before_update"]["root"]).resolve() != ru_root.resolve():
        raise RuntimeError("Backup manifest belongs to a different Russian output root")


def synchronize(en_root: Path, ru_root: Path, apply: bool) -> dict[str, Any]:
    en_index, _ = build_json_index(en_root)
    ru_index, _ = build_json_index(ru_root)
    changed: list[str] = []
    added: list[str] = []
    for normalized, en_path in sorted(en_index.items()):
        relative = canonical_path(en_path.relative_to(en_root))
        target = ru_root / Path(relative)
        english = load_json(en_path)
        if normalized not in ru_index:
            merged = deepcopy(english)
            added.append(relative)
        else:
            merged = merge_structure(english, load_json(ru_index[normalized]))
        current = load_json(target) if target.exists() else None
        if merged != current:
            changed.append(relative)
            if apply:
                write_json(target, merged)
    return {
        "english_files": len(en_index),
        "russian_files_before": len(ru_index),
        "changed_files": changed,
        "added_files": added,
        "applied": apply,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--en", type=Path, required=True)
    parser.add_argument("--ru", type=Path, required=True)
    parser.add_argument("--backup-manifest", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verified_backup(args.backup_manifest.resolve(), args.ru.resolve())
    result = synchronize(args.en.resolve(), args.ru.resolve(), args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
