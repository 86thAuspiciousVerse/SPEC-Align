"""Read Codex app-server hook trust and MCP inventory; never change trust."""
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    executable = shutil.which('codex')
    if not executable:
        raise SystemExit('Codex CLI is not installed')
    process = subprocess.Popen([executable, 'app-server', '--stdio'], cwd=root,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, encoding='utf-8')
    messages = queue.Queue()

    def read():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                pass

    threading.Thread(target=read, daemon=True).start()

    def request(ident, method, params):
        process.stdin.write(json.dumps({'id': ident, 'method': method, 'params': params}) + '\n')
        process.stdin.flush()
        deadline = time.monotonic() + 25
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(method)
            try:
                message = messages.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError(method) from None
            if message.get('id') == ident:
                if 'error' in message:
                    raise RuntimeError(f'{method}: RPC error {message["error"].get("code")}')
                return message['result']

    evidence = {'scope': 'fresh CLI app-server, not the running desktop session'}
    try:
        request(1, 'initialize', {'clientInfo': {'name': 'specalign_diagnostic', 'version': '1'},
                                  'capabilities': {'experimentalApi': True}})
        process.stdin.write('{"method":"initialized"}\n')
        process.stdin.flush()
        result = request(2, 'hooks/list', {'cwds': [str(root)]})
        evidence['hooks'] = [
            {key: hook.get(key) for key in ('eventName', 'source', 'sourcePath', 'enabled',
                                           'trustStatus', 'currentHash')}
            for entry in result['data'] for hook in entry['hooks']
            if 'specalign' in hook.get('command', '').lower()
        ]
        evidence['hook_error_count'] = sum(len(entry['errors']) for entry in result['data'])
        try:
            result = request(3, 'mcpServerStatus/list', {'detail': 'toolsAndAuthOnly', 'limit': 100})
            evidence['mcp'] = [
                {'name': server['name'], 'tools': sorted(server.get('tools', {}))}
                for server in result['data'] if server['name'] == 'specalign'
            ]
        except (TimeoutError, RuntimeError) as error:
            evidence['mcp_unresolved'] = str(error)
    finally:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    destination = root / '.specalign/diagnostics/host-status.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()

