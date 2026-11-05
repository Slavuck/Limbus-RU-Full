"""Audit a game patch against the previous EN/KR index and the current RU pack.

    python scripts/audit_patch_localization.py --version 1.118.1 --source GAME/Localize
        --ru Localize/Limbus-RU-Full --baseline-dir reports/1.118.0
        --report-dir reports/1.118.1

Run the recursive audit and write patch_findings.json alongside the detailed
reports. The command exits nonzero if the underlying audit finds blockers.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from .audit_current_localization import default_ru, default_source
    from .audit_game_update import read_rows
    from .audit_localization_diff import canonical_path
    from .localization_common import load_json, write_json
except ImportError:
    from audit_current_localization import default_ru, default_source
    from audit_game_update import read_rows
    from audit_localization_diff import canonical_path
    from localization_common import load_json, write_json


def collect_findings(report_dir):
    summary = load_json(report_dir / 'update_summary.json')
    delta = load_json(report_dir / 'source_file_delta.json')
    pairing = load_json(report_dir / 'file_pairing.json')
    korean_only = {name.casefold() for name in pairing['korean_without_english']}
    changed_korean_only = [name for state in ('added', 'changed') for name in delta['kr'][state]
                           if canonical_path(name).casefold() in korean_only]

    pending = {}
    for name in ('untranslated', 'changed_source', 'format_errors'):
        for row in read_rows(report_dir / f'{name}.jsonl'):
            if row['status'] != 'pending':
                continue
            fields = ('queue_id', 'relative_path', 'json_path', 'semantic_path', 'review_reason',
                      'english', 'korean', 'current_russian')
            item = pending.setdefault(row['queue_id'], {key: row[key] for key in fields})
            item.setdefault('reports', []).append(name)

    return {
        'target_version': summary['target_version'],
        'blocking_count': summary['blocking_count'],
        'source_file_delta': delta,
        'missing_russian_files': pairing['english_without_russian'],
        'changed_korean_only_files': changed_korean_only,
        'pending_text': list(pending.values()),
        'structural_reports': ['missing_structure.jsonl', 'technical_mismatches.jsonl', 'obsolete_russian.jsonl'],
    }


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=default_source(root))
    parser.add_argument('--ru', type=Path, default=default_ru(root))
    parser.add_argument('--version', required=True)
    parser.add_argument('--baseline-dir', type=Path, required=True)
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.source is None:
        parser.error('Specify --source or provide input/расположение языковых пакетов.txt')
    for path in (args.source / 'en', args.source / 'kr', args.ru):
        if not path.is_dir():
            parser.error(f'Folder does not exist: {path}')
        if args.report_dir.resolve().is_relative_to(path.resolve()):
            parser.error('Reports must be outside the localization directories')
    for name in ('source_index.jsonl', 'source_manifest.json'):
        if not (args.baseline_dir / name).is_file():
            parser.error(f'Baseline file does not exist: {args.baseline_dir / name}')
    if args.report_dir.resolve() == args.baseline_dir.resolve():
        parser.error('Report directory must differ from the baseline directory')

    command = [sys.executable, str(Path(__file__).with_name('audit_current_localization.py')),
               '--source', str(args.source), '--ru', str(args.ru), '--version', args.version,
               '--baseline-dir', str(args.baseline_dir), '--report-dir', str(args.report_dir)]
    result = subprocess.run(command, capture_output=True, encoding='utf-8',
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    if result.stderr:
        print(result.stderr, file=sys.stderr, end='')
    if not result.stdout:
        return result.returncode or 1
    print(result.stdout, end='')
    # The audit emits a single JSON summary on normal completion, including
    # when --check reports blockers. Do not reuse old reports after a failure.
    json.loads(result.stdout)
    findings = collect_findings(args.report_dir)
    write_json(args.report_dir / 'patch_findings.json', findings)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
