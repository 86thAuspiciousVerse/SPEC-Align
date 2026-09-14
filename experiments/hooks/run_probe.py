"""Run a bounded, isolated CLI probe; does not install global/project hooks."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
workspace = root / 'workspace'
workspace.mkdir(exist_ok=True)
command = f'"{sys.executable}" "{root / "probe.py"}"'
config = 'hooks.PostToolUse=[{hooks=[{type="command",command=' + json.dumps(command) + '}]}]'
args = [shutil.which('codex.cmd') or 'codex', 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check', '--dangerously-bypass-hook-trust', '-C', str(workspace), '-s', 'read-only', '-c', config, '--json', 'Run a shell command that prints the word READY. Then report any hook-delivered token, or NO_TOKEN if none. Do not read any files or use other tools.']
event_log = root / 'events.jsonl'
event_log.write_text('', encoding='utf-8')
# Capture directly to files: inherited pipes from cmd.exe grandchildren can keep
# communicate() alive beyond its nominal timeout on Windows.
with (root / 'run.jsonl').open('wb') as output, (root / 'run.stderr.txt').open('wb') as errors:
    process = subprocess.Popen(args, stdout=output, stderr=errors)
    try:
        process.wait(timeout=70)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=10)
        else:
            process.kill()
        process.wait(timeout=10)
        print('Probe timeout; stop investigation and continue core implementation.')
result = (root / 'run.jsonl').read_text(encoding='utf-8', errors='replace')
finals = []
for line in result.splitlines():
    try:
        item = json.loads(line).get('item', {})
        if item.get('type') == 'agent_message':
            finals.append(item.get('text', ''))
    except json.JSONDecodeError:
        pass
print(json.dumps({'exit_code': process.returncode,
                  'hook_ran': bool(event_log.read_text(encoding='utf-8').strip()),
                  'token_in_agent_message': any('SPECALIGN_HOOK_DELIVERED_7391' in text for text in finals)}))

