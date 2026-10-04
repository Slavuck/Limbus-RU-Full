"""Audit a game update recursively without modifying translations or originals.

Uses the input locator by default. --baseline-index compares visible EN/KR
fields by identity; --baseline-manifest additionally reports SHA-256 changes
for every source file, including Korean-only files and non-text changes.
"""
import json
from pathlib import Path
from audit_localization_diff import audit, build_parser, detailed_manifest
from localization_common import EN_DIR, KR_DIR, OUT_DIR, load_json, write_json


def file_delta(before, after):
    old = {item['path']: item['sha256'] for item in before['files']}
    new = {item['path']: item['sha256'] for item in after['files']}
    return {'added': sorted(new.keys() - old.keys()),
            'deleted': sorted(old.keys() - new.keys()),
            'changed': sorted(key for key in old.keys() & new.keys() if old[key] != new[key])}


def main():
    parser = build_parser()
    for action in parser._actions:
        if action.dest in ('en', 'kr', 'ru'):
            action.required = False
    parser.set_defaults(en=EN_DIR, kr=KR_DIR, ru=OUT_DIR)
    parser.add_argument('--baseline-manifest', type=Path)
    args = parser.parse_args()
    if args.baseline_manifest:
        previous = load_json(args.baseline_manifest)
        delta = {lang: file_delta(previous['input_' + lang], detailed_manifest(root))
                 for lang, root in [('en', args.en), ('kr', args.kr)]}
        write_json(args.report_dir / 'source_file_delta.json', delta)
    result = audit(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(args.check and result['blocking_count'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
