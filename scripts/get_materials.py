"""Retrieve this release's complete, checksummed research archive."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import stat
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Use a downloaded archive instead of retrieving it.')
    args = parser.parse_args()
    spec = json.loads((ROOT / 'RELEASE_ASSETS.json').read_text())['complete_archive']
    archive = args.archive
    if archive is None:
        folder = ROOT / 'release_assets'
        folder.mkdir(exist_ok=True)
        archive = folder / spec['name']
        if not archive.exists():
            temporary = archive.with_suffix('.download')
            request = urllib.request.Request(spec['url'], headers={'User-Agent': 'Strategy-RDM-replication/2.0.0'})
            try:
                with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as out:
                    while block := response.read(1024 * 1024):
                        out.write(block)
                temporary.replace(archive)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
    if archive.stat().st_size != spec['bytes'] or sha256(archive) != spec['sha256']:
        raise SystemExit('Archive checksum mismatch; nothing has been extracted.')
    manifest = json.loads((ROOT / 'MATERIALS_MANIFEST.json').read_text())
    expected = manifest['files']
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        if len(names) != len(set(names)):
            raise SystemExit('Duplicate archive paths; nothing has been extracted.')
        if set(names) != set(expected) | {'MATERIALS_MANIFEST.json'}:
            raise SystemExit('Archive inventory differs from the release manifest.')
        if zipped.read('MATERIALS_MANIFEST.json') != (ROOT / 'MATERIALS_MANIFEST.json').read_bytes():
            raise SystemExit('Archive manifest differs from this checkout.')
        # Check all paths and contents before changing the checkout.
        for name in names:
            path = PurePosixPath(name)
            info = zipped.getinfo(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or stat.S_ISLNK(info.external_attr >> 16):
                raise SystemExit('Unsafe archive path: ' + name)
            if name == 'MATERIALS_MANIFEST.json':
                continue
            content = zipped.read(name)
            record = expected[name]
            if len(content) != record['bytes'] or hashlib.sha256(content).hexdigest() != record['sha256']:
                raise SystemExit('Archived file differs from its manifest: ' + name)
            target = ROOT / name
            if target.exists() and sha256(target) != record['sha256']:
                raise SystemExit('Existing file has local changes; preserve them before extracting: ' + name)
        created = 0
        for name in expected:
            target = ROOT / name
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + '.unpacking')
            temporary.write_bytes(zipped.read(name))
            os.replace(temporary, target)
            created += 1
    print(json.dumps({'status': 'PASS', 'created_files': created, 'checked_files': len(expected)}))

if __name__ == '__main__':
    main()
