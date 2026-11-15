"""Audit the current EN/KR localization against the RU pack.

    python scripts/audit_patch_localization.py --version 1.118.1 --source GAME/Localize
        --ru Localize/Limbus-RU-Full --baseline-dir reports/1.118.0
        --report-dir reports/1.118.1

Supply --baseline-dir to include changed and deleted source strings.
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


def collect_findings(report_dir, *, compare_baseline=True):
    summary = load_json(report_dir / 'update_summary.json')
    delta = load_json(report_dir / 'source_file_delta.json') if compare_baseline else None
    pairing = load_json(report_dir / 'file_pairing.json')
    korean_only = {name.casefold() for name in pairing['korean_without_english']}
    changed_korean_only = None
    if delta is not None:
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
        'korean_without_english': pairing['korean_without_english'],
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
    parser.add_argument('--baseline-dir', type=Path,
                        help='Previous audit directory, for source changes and deletions')
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.source is None:
        parser.error('Specify --source or provide input/расположение языковых пакетов.txt')
    for path in (args.source / 'en', args.source / 'kr', args.ru):
        if not path.is_dir():
            parser.error(f'Folder does not exist: {path}')
        if args.report_dir.resolve().is_relative_to(path.resolve()):
            parser.error('Reports must be outside the localization directories')
    command = [sys.executable, str(Path(__file__).with_name('audit_current_localization.py')),
               '--source', str(args.source), '--ru', str(args.ru), '--version', args.version,
               '--report-dir', str(args.report_dir)]
    if args.baseline_dir is not None:
        if args.report_dir.resolve() == args.baseline_dir.resolve():
            parser.error('Report directory must differ from the baseline directory')
        command += ['--baseline-dir', str(args.baseline_dir)]
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
    findings = collect_findings(args.report_dir, compare_baseline=args.baseline_dir is not None)
    write_json(args.report_dir / 'patch_findings.json', findings)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
