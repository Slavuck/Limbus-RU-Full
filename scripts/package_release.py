"""Build and verify a release ZIP from the finalized audit, including fonts."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from audit_localization_diff import detailed_manifest
from localization_common import load_json, write_json

CONFIG = {'lang': 'Limbus-RU-Full', 'titleFont': '', 'contextFont': '',
          'samplingPointSize': 78, 'padding': 5}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--ru', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    final = load_json(args.work_dir / 'final_manifest.json')
    if final['audit_summary']['blocking_count']:
        raise RuntimeError('Final audit has blockers')
    current = detailed_manifest(args.ru)
    if current['sha256'] != final['output_after']['sha256']:
        raise RuntimeError('Localization changed after final verification')
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    temp = args.destination.with_suffix('.zip.tmp')
    files = {item['path']: item['sha256'] for item in current['files']}
    with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr('config.json', json.dumps(CONFIG, ensure_ascii=False, indent=2) + '\n')
        for name in sorted(files):
            archive.write(args.ru / name, 'Limbus-RU-Full/' + name)
    with zipfile.ZipFile(temp) as archive:
        expected = {'config.json'} | {'Limbus-RU-Full/' + name for name in files}
        if archive.testzip() is not None or len(archive.namelist()) != len(expected) or set(archive.namelist()) != expected:
            raise RuntimeError('Invalid archive CRC or layout')
        if json.loads(archive.read('config.json')) != CONFIG:
            raise RuntimeError('Config differs from requested contents')
        for name, digest in files.items():
            content = archive.read('Limbus-RU-Full/' + name)
            if hashlib.sha256(content).hexdigest() != digest:
                raise RuntimeError(f'Archive differs from localization: {name}')
            if name.lower().endswith('.json'):
                json.loads(content.decode('utf-8-sig'))
    temp.replace(args.destination)
    result = {'archive': str(args.destination.resolve()),
              'sha256': hashlib.sha256(args.destination.read_bytes()).hexdigest(),
              'bytes': args.destination.stat().st_size, 'files': len(files) + 1,
              'output_sha256': current['sha256'], 'config': CONFIG}
    write_json(args.destination.parent / 'package_verification.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
