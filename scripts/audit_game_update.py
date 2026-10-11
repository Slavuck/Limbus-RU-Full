"""Read-only recursive EN/KR/RU audit, including removed source strings.

Example:
  python scripts/audit_game_update.py --en GAME/en --kr GAME/kr --ru Localize/Limbus-RU-Full \
    --baseline-index previous/source_index.jsonl --baseline-manifest previous/backup_manifest.json \
    --target-version 1.116.2 --report-dir reports/1.116.2 --check

Reports must be outside all input trees. No translation or original is modified.
"""
import json
from pathlib import Path
try:
    from .audit_localization_diff import (
        audit, build_parser, canonical_path, detailed_manifest, iter_string_semantic_paths,
    )
    from .localization_common import build_json_index, load_json, write_json, write_jsonl
except ImportError:
    from audit_localization_diff import (
        audit, build_parser, canonical_path, detailed_manifest, iter_string_semantic_paths,
    )
    from localization_common import build_json_index, load_json, write_json, write_jsonl


def read_rows(path):
    with path.open(encoding='utf-8-sig') as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def delta(before, after):
    old = {row['path']: row['sha256'] for row in before['files']}
    new = {row['path']: row['sha256'] for row in after['files']}
    return {'added': sorted(new.keys() - old.keys()), 'deleted': sorted(old.keys() - new.keys()),
            'changed': sorted(key for key in old.keys() & new.keys() if old[key] != new[key])}


def removed_source_rows(previous_rows, current_rows, ru_root):
    current = {(canonical_path(r['normalized_file']).casefold(), tuple(r['semantic_path']))
               for r in current_rows}
    ru_index, _ = build_json_index(ru_root)
    ru_locators = {}
    deleted, obsolete = [], []
    for old in previous_rows:
        relative = canonical_path(old['normalized_file'])
        locator = (relative.casefold(), tuple(old.get('semantic_path', [])))
        if locator in current:
            continue
        row = {'relative_path': relative, 'semantic_path': old.get('semantic_path'),
               'previous_english': old.get('new_english_value'),
               'previous_korean': old.get('new_korean_value')}
        deleted.append(row)
        if relative.casefold() not in ru_locators:
            path = ru_index.get(relative.casefold())
            ru_locators[relative.casefold()] = set(iter_string_semantic_paths(load_json(path))) if path else set()
        if locator[1] in ru_locators[relative.casefold()]:
            obsolete.append(row)
    return deleted, obsolete


def main():
    parser = build_parser()
    parser.add_argument('--baseline-manifest', type=Path,
                        help='Previous manifest containing input_en.files and input_kr.files')
    args = parser.parse_args()
    report = args.report_dir.resolve()
    for root in (args.en, args.kr, args.ru):
        if report.is_relative_to(root.resolve()):
            parser.error('--report-dir must be outside the EN, KR and RU trees')
    manifests = {lang: detailed_manifest(root) for lang, root in [('en', args.en), ('kr', args.kr)]}
    write_json(report / 'source_manifest.json', {'input_' + lang: data for lang, data in manifests.items()})
    if args.baseline_manifest:
        previous = load_json(args.baseline_manifest)
        for lang in manifests:
            if 'files' not in previous.get('input_' + lang, {}):
                parser.error('Baseline manifest must contain per-file hashes; use backup_manifest.json or source_manifest.json')
        write_json(report / 'source_file_delta.json',
                   {lang: delta(previous['input_' + lang], data) for lang, data in manifests.items()})
    summary = audit(args)
    deleted = []
    obsolete = []
    if args.baseline_index:
        deleted, obsolete = removed_source_rows(read_rows(args.baseline_index),
                                               read_rows(report / 'source_index.jsonl'), args.ru)
    write_jsonl(report / 'deleted_source.jsonl', deleted)
    write_jsonl(report / 'obsolete_russian.jsonl', obsolete)
    summary['counts']['deleted_source_strings'] = len(deleted)
    summary['counts']['obsolete_russian_strings'] = len(obsolete)
    summary['blocking_count'] += len(obsolete)
    write_json(report / 'update_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return int(args.check and summary['blocking_count'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
