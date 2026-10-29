"""Build this native starter deterministically; no Core checkout is needed to build."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
from application_contract import VERSION, WHEEL_VERSION, descriptors

ROOT = Path(__file__).resolve().parent


def write(archive, name, payload):
    info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload)


def package_files():
    manifest, application, ui = descriptors()
    sources = {'starter_application/' + p.name: p.read_bytes().replace(b'\r\n', b'\n')
               for p in sorted((ROOT / 'service/starter_application').glob('*.py'))}
    dist = f'starter_application-{WHEEL_VERSION}.dist-info'
    sources[dist + '/METADATA'] = f'Metadata-Version: 2.1\nName: starter-application\nVersion: {WHEEL_VERSION}\n'.encode()
    sources[dist + '/WHEEL'] = b'Wheel-Version: 1.0\nGenerator: starter-application\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, payload in sorted(sources.items()):
        writer.writerow([name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b'=').decode(), len(payload)])
    writer.writerow([dist + '/RECORD', '', ''])
    sources[dist + '/RECORD'] = record.getvalue().encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, payload in sorted(sources.items()):
            write(archive, name, payload)
    wheel = output.getvalue()
    application['service']['artifact_sha256'] = hashlib.sha256(wheel).hexdigest()
    files = {name: json.dumps(value, ensure_ascii=False, sort_keys=True).encode() for name, value in
             [('manifest.json', manifest), ('application-extension.json', application), ('compiled-ui.json', ui)]}
    files[application['service']['artifact']] = wheel
    for path in sorted((ROOT / 'source/frontend').rglob('*')):
        if path.suffix in {'.vue', '.ts', '.css', '.json'}:
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes().replace(b'\r\n', b'\n')
    return files


def build_package():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, payload in sorted(package_files().items()):
            write(archive, name, payload)
    return output.getvalue()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    payload = build_package()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as target:
        target.write(payload)
    print('SHA256 ' + hashlib.sha256(payload).hexdigest())
