"""Bundle an already-built exe with docs, dependency inventory and license texts."""
import hashlib
import importlib.metadata
import json
import platform
import shutil
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = importlib.metadata.version('spec-align')
(root / 'build').mkdir(exist_ok=True)
staging = Path(tempfile.mkdtemp(prefix='release-', dir=root / 'build'))
folder = staging / f'specalign-{version}-windows-x64'
folder.mkdir()
shutil.copy2(root / 'dist/windows/specalign.exe', folder / 'specalign.exe')
shutil.copy2(root / 'packaging/WINDOWS-README.md', folder / 'README.md')
shutil.copy2(root / 'docs/PROTOCOL.md', folder / 'PROTOCOL.md')
licenses = folder / 'licenses'
licenses.mkdir(exist_ok=True)
inventory = []
for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
    name = dist.metadata['Name']
    copied = []
    for file in dist.files or []:
        # Distribution metadata paths only; never copy credentials or environment files.
        if '.dist-info/' not in str(file).replace('\\', '/'):
            continue
        if not any(word in file.name.lower() for word in ('license', 'copying', 'notice')):
            continue
        source = dist.locate_file(file)
        if source.is_file():
            dest = licenses / name / str(file).split('.dist-info/', 1)[-1]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            copied.append(dest.relative_to(folder).as_posix())
    inventory.append({'name': name, 'version': dist.version, 'license_files': copied})
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if not python_license.is_file():
    raise SystemExit('Python license missing; do not publish incomplete bundle')
shutil.copy2(python_license, licenses / 'PYTHON-LICENSE.txt')
(folder / 'BUILD-ENVIRONMENT.json').write_text(json.dumps({
    'python': platform.python_version(), 'architecture': platform.machine(),
    'note': 'Build environment inventory; includes build/test tooling not necessarily embedded.',
    'distributions': inventory,
}, indent=2) + '\n', encoding='utf-8')
(folder / 'SHA256SUMS.txt').write_text(hashlib.sha256((folder/'specalign.exe').read_bytes()).hexdigest() + '  specalign.exe\n', encoding='utf-8')
archive = Path(shutil.make_archive(str(root / 'dist' / folder.name), 'zip', folder.parent, folder.name))
archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n', encoding='utf-8')
print(archive)

