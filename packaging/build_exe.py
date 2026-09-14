"""Build a Windows single-file executable using the active isolated environment."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if sys.platform != 'win32':
    raise SystemExit('Build Windows releases on Windows')
subprocess.run([
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
    '--console', '--name', 'specalign', '--paths', str(root),
    '--collect-data', 'specalign',
    '--copy-metadata', 'spec-align', '--recursive-copy-metadata', 'mcp',
    '--distpath', str(root / 'dist/windows'), '--workpath', str(root / 'build/exe'),
    '--specpath', str(root / 'build'), str(root / 'packaging/entrypoint.py'),
], cwd=root, check=True)

