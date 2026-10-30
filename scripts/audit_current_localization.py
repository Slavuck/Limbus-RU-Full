"""Convenient read-only recursive audit of installed EN/KR against a RU pack.

Example:
 python scripts/audit_current_localization.py --source "C:/Games/Limbus/Localize" \
   --ru Localize/Limbus-RU-Full --version 1.117.1 --report-dir reports/1.117.1

--baseline-dir may point at an earlier audit directory containing source_index.jsonl,
source_manifest.json and queues/. The full audit runs with --check by default.
Reports must be outside the original and translation folders.
"""
import argparse
import subprocess
import sys
from pathlib import Path


def default_source(root):
    """Use supplied local EN/KR trees or the owner's installed-game locator."""
    if all((root / 'input' / lang).is_dir() for lang in ('en', 'kr')):
        return root / 'input'
    locator = root / 'input/расположение языковых пакетов.txt'
    if locator.is_file():
        lines = locator.read_text(encoding='utf-8-sig').splitlines()
        if lines and lines[0].strip():
            return Path(lines[0].strip().strip('"'))
    return None


def default_ru(root):
    for relative in ('output/Limbus-RU-Full', 'Localize/Limbus-RU-Full'):
        candidate = root / relative
        if candidate.is_dir():
            return candidate
    return root / 'Localize/Limbus-RU-Full'


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=default_source(root),
                        help='Game Localize directory containing en/ and kr/; defaults to input or its locator')
    parser.add_argument('--ru', type=Path, default=default_ru(root))
    parser.add_argument('--version', required=True)
    parser.add_argument('--report-dir', type=Path, required=True)
    parser.add_argument('--baseline-dir', type=Path)
    args = parser.parse_args()
    if args.source is None:
        parser.error('Specify --source or provide input/расположение языковых пакетов.txt')
    for path in (args.source / 'en', args.source / 'kr', args.ru):
        if not path.is_dir():
            parser.error(f'Folder does not exist: {path}')
    command = [sys.executable, str(Path(__file__).with_name('audit_game_update.py')),
               '--en', str(args.source / 'en'), '--kr', str(args.source / 'kr'),
               '--ru', str(args.ru), '--target-version', args.version,
               '--mode', 'full-review', '--report-dir', str(args.report_dir), '--check']
    if args.baseline_dir:
        for name, flag in [('source_index.jsonl', '--baseline-index'),
                           ('source_manifest.json', '--baseline-manifest')]:
            path = args.baseline_dir / name
            if not path.is_file():
                parser.error(f'Baseline file does not exist: {path}')
            command += [flag, str(path)]
        if (args.baseline_dir / 'queues').is_dir():
            command += ['--prior-queues', str(args.baseline_dir / 'queues')]
    return subprocess.call(command)


if __name__ == '__main__':
    raise SystemExit(main())
