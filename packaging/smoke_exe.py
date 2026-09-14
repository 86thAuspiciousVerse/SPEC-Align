"""Run an actual copied exe outside the repository; clients need Python, exe does not."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def main():
    source = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='specalign-exe-') as directory:
        base = Path(directory)
        exe = base / '工具 with spaces' / 'specalign.exe'
        exe.parent.mkdir()
        shutil.copy2(source, exe)
        root = base / '项目 space'
        env = {k: v for k, v in os.environ.items() if not k.startswith(('PYTHON', '_PYI'))}
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')

        def run(*args):
            result = subprocess.run([str(exe), '--root', str(root), *args], cwd=base,
                                    env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
            assert result.returncode == 0, (args, result.stdout, result.stderr)
            return result.stdout

        run('init')
        (root / 'spec/a.md').write_text('<!-- spec\nid: A\nstatus: active\n-->\nLocal only.\n<!-- /spec -->\n\n'
            '<!-- spec\nid: B\nstatus: active\ndepends_on: [A]\n-->\nLocal design.\n<!-- /spec -->\n', encoding='utf-8')
        installed = json.loads(run('install', '--codex'))
        assert installed['mcp_command'] == [str(exe), '--root', str(root), 'serve']
        skill = root / '.agents/skills/spec-align/SKILL.md'
        assert skill.read_text(encoding='utf-8') == Path('specalign/assets/SKILL.md').read_text(encoding='utf-8')
        hook = json.loads((root / '.codex/hooks.json').read_text(encoding='utf-8'))['hooks']['PostToolUse'][0]['hooks'][0]
        started = time.monotonic()
        result = subprocess.run(hook['commandWindows'], shell=True, cwd=base, env=env,
            input=json.dumps({'hook_event_name':'PostToolUse','session_id':'exe-smoke'}),
            capture_output=True, text=True, encoding='utf-8', timeout=15)
        assert result.returncode == 0, result.stderr
        assert 'needs_review' in json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
        elapsed = time.monotonic() - started

        async def mcp():
            with anyio.fail_after(40):
                async with stdio_client(StdioServerParameters(command=str(exe), args=['--root',str(root),'serve'],env=env,cwd=str(base))) as (reader,writer):
                    async with ClientSession(reader,writer) as client:
                        await client.initialize()
                        assert len((await client.list_tools()).tools) == 9
                        async def call(name, args):
                            response = await client.call_tool(name,args)
                            assert not response.isError, response
                            return json.loads(response.content[0].text)
                        report = await call('spec_check', {})
                        assert 'items' not in report and report['unresolved_count'] == 1
                        await call('spec_context', {'items':['B'],'related':True})
                        report = await call('spec_review_batch', {'snapshot':report['snapshot'], 'reviews':[{'item':'B','reason':'Fixture: local design matches local requirement.'}]})
                        assert report['findings'] == []
        anyio.run(mcp)
        assert json.loads(run('check','--detail','summary'))['findings'] == []
        run('backup',str(base/'ledger.sqlite3'))
        run('uninstall','--codex')
        print(json.dumps({'exe_smoke':'passed','mcp_tools':9,'hook_seconds':round(elapsed,3),
                          'python_removed_from_child_path':True,'unicode_spaces':True}))


if __name__ == '__main__':
    main()

