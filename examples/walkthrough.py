"""Exercise the real CLI in a disposable fixture, never review user documents."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(root, *args, expected=0, event=None):
    result = subprocess.run([sys.executable, '-m', 'specalign', '--root', str(root), *args],
                            input=json.dumps(event) if event else None,
                            capture_output=True, text=True, encoding='utf-8', timeout=20,
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    if result.returncode != expected:
        raise RuntimeError(f'{args}: expected {expected}, got {result.returncode}: {result.stderr}')
    return result


def main():
    with tempfile.TemporaryDirectory(prefix='specalign-demo-') as directory:
        root = Path(directory)
        run(root, 'init')
        fixture = root / 'spec' / 'storage.md'
        fixture.write_text((Path(__file__).parent / 'minimal/spec/storage.md').read_text(encoding='utf-8'), encoding='utf-8')
        initial = json.loads(run(root, 'check', expected=2).stdout)
        run(root, 'review', 'DEC-STORAGE', '--snapshot', initial['snapshot'],
            '--reason', 'Scripted fixture assertion: local SQLite meets the offline requirement.')
        print('PASS initial review recorded')

        fixture.write_text(fixture.read_text(encoding='utf-8').replace(
            'Core operations must work offline.', 'Core operations and backups must work offline.'), encoding='utf-8')
        event = {'hook_event_name': 'PostToolUse', 'session_id': 'walkthrough'}
        notification = json.loads(run(root, 'hook', event=event).stdout)
        if 'needs_review DEC-STORAGE' not in notification['hookSpecificOutput']['additionalContext']:
            raise RuntimeError('Missing change reminder')
        if json.loads(run(root, 'hook', event=event).stdout) != {}:
            raise RuntimeError('Duplicate reminder was not suppressed')
        print('PASS hook protocol reminder and dedup (no harness involved)')

        evidence = json.loads(run(root, 'explain', 'DEC-STORAGE', expected=2).stdout)
        if not evidence['review'] or not any(c['item'] == 'REQ-OFFLINE' and 'backups' in c['diff'] for c in evidence['changes']):
            raise RuntimeError('Missing prior review or requirement diff')
        print('PASS explain exposes reviewed baseline and upstream diff')

        run(root, 'review', 'DEC-STORAGE', '--snapshot', initial['snapshot'], '--reason', 'Stale fixture observation', expected=3)
        print('PASS stale snapshot rejected')
        run(root, 'review', 'DEC-STORAGE', '--snapshot', evidence['snapshot'],
            '--reason', 'Scripted fixture assertion: local SQLite remains compatible with offline backups.')
        run(root, 'check')
        print('PASS current review clears pending finding')
    print('Disposable fixture removed; no user document or audit database was changed.')


if __name__ == '__main__':
    main()

