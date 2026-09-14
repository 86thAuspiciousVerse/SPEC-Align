import json
import os
import subprocess
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from specalign.integration import doctor, git_check, install, uninstall
from specalign.core import ProtocolError
from test_runtime import block, project


def test_install_idempotent_preserves_siblings_and_modified_skill(project):
    runtime, spec = project
    config = runtime.root / '.codex/hooks.json'
    config.parent.mkdir()
    unrelated = {'type': 'command', 'command': 'echo other'}
    toml = runtime.root / '.codex/config.toml'
    toml.write_text('model = "example-model"\n[mcp_servers.other]\ncommand = "other"\n', encoding='utf-8')
    original_toml = toml.read_text(encoding='utf-8')
    config.write_text(json.dumps({'description': 'Keep', 'hooks': {'PostToolUse': [{'hooks': [unrelated]}]}}), encoding='utf-8')
    assert install(runtime.root, codex=True)['changed']
    before = config.read_bytes()
    assert install(runtime.root, codex=True)['changed'] == []
    assert config.read_bytes() == before
    assert doctor(runtime.root)['configured_events'] == ['PostToolUse', 'Stop']
    skill = runtime.root / '.agents/skills/spec-align/SKILL.md'
    skill.write_text(skill.read_text(encoding='utf-8') + '\nLocal additions\n', encoding='utf-8')
    with pytest.raises(ProtocolError):
        install(runtime.root, codex=True)
    result = uninstall(runtime.root, codex=True)
    assert str(skill) in result['preserved']
    assert json.loads(config.read_text(encoding='utf-8')) == {'description': 'Keep', 'hooks': {'PostToolUse': [{'hooks': [unrelated]}]}}
    assert toml.read_text(encoding='utf-8') == original_toml


def test_installed_hook_command_runs_without_model(project):
    runtime, spec = project
    (spec / 'bad.md').write_text(block('B', deps=['MISSING']), encoding='utf-8')
    install(runtime.root, codex=True)
    config = json.loads((runtime.root / '.codex/hooks.json').read_text(encoding='utf-8'))
    handler = config['hooks']['PostToolUse'][0]['hooks'][0]
    command = handler.get('commandWindows', handler['command']) if os.name == 'nt' else handler['command']
    result = subprocess.run(command, shell=True, cwd=runtime.root,
                            input=json.dumps({'hook_event_name': 'PostToolUse', 'session_id': 'installed'}),
                            capture_output=True, text=True, encoding='utf-8',
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, timeout=20)
    assert result.returncode == 0, result.stderr
    assert 'missing_target' in json.loads(result.stdout)['hookSpecificOutput']['additionalContext']


def test_git_gate_uses_index_not_worktree(project):
    runtime, spec = project
    subprocess.run(['git', 'init', '-q', str(runtime.root)], check=True)
    file = spec / 'bad.md'
    file.write_text(block('B', deps=['MISSING']), encoding='utf-8')
    subprocess.run(['git', '-C', str(runtime.root), 'add', 'spec'], check=True)
    file.write_text(block('B'), encoding='utf-8')
    assert not git_check(runtime.root)['valid']
    subprocess.run(['git', '-C', str(runtime.root), 'add', 'spec'], check=True)
    assert git_check(runtime.root)['valid']
    install(runtime.root, git_hook=True)
    before = (runtime.root / '.git/hooks/pre-commit').read_bytes()
    assert install(runtime.root, git_hook=True)['changed'] == []
    assert (runtime.root / '.git/hooks/pre-commit').read_bytes() == before
    uninstall(runtime.root, git_hook=True)
    assert not (runtime.root / '.git/hooks/pre-commit').exists()


def test_mcp_real_stdio_roundtrip(project):
    runtime, spec = project
    (spec / 'a.md').write_text(block('A') + '\n' + block('B', deps=['A']), encoding='utf-8')

    async def scenario():
        server = StdioServerParameters(command=sys.executable,
                                       args=['-m', 'specalign', '--root', str(runtime.root), 'serve'],
                                       env={'PYTHONIOENCODING': 'utf-8'})
        with anyio.fail_after(30):
            async with stdio_client(server) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    names = {t.name for t in (await client.list_tools()).tools}
                    assert {'spec_check', 'spec_explain', 'spec_review', 'spec_decide'}.issubset(names)
                    checked = await client.call_tool('spec_check', {})
                    assert not checked.isError
                    report = json.loads(checked.content[0].text)
                    assert 'items' not in report
                    full = await client.call_tool('spec_check', {'detail':'full'})
                    assert 'A' in json.loads(full.content[0].text)['items']
                    contextual = await client.call_tool('spec_context', {'items':['A','B'], 'related':True})
                    assert not contextual.isError
                    batch = await client.call_tool('spec_review_batch', {'snapshot': report['snapshot'], 'reviews':[{'item':'B','reason':'Fixture batch evidence'}]})
                    assert not batch.isError and json.loads(batch.content[0].text)['batch_id']
                    plan = await client.call_tool('spec_migration_plan', {})
                    assert not plan.isError and json.loads(plan.content[0].text)['applied'] is False

                    reviewed = await client.call_tool('spec_review', {'item': 'B', 'snapshot': report['snapshot'], 'reason': 'Fixture review'})
                    assert not reviewed.isError
                    assert json.loads(reviewed.content[0].text)['findings'] == []
                    invalid = await client.call_tool('spec_context', {'item': 'B', 'max_chars': -1})
                    assert invalid.isError
    anyio.run(scenario)


def test_modified_git_hook_is_never_overwritten_or_deleted(project):
    runtime, spec = project
    subprocess.run(['git', 'init', '-q', str(runtime.root)], check=True)
    install(runtime.root, git_hook=True)
    path = runtime.root / '.git/hooks/pre-commit'
    path.write_text(path.read_text(encoding='utf-8') + '\necho user-check\n', encoding='utf-8')
    original = path.read_bytes()
    with pytest.raises(ProtocolError):
        install(runtime.root, git_hook=True)
    assert path.read_bytes() == original
    result = uninstall(runtime.root, git_hook=True)
    assert str(path) in result['preserved']
    assert path.read_bytes() == original


@pytest.mark.parametrize('managed_root', ['./spec', 'docs\\spec'])
def test_staged_roots_are_normalized_and_worktree_config_is_ignored(project, managed_root):
    runtime, spec = project
    import yaml
    subprocess.run(['git', 'init', '-q', str(runtime.root)], check=True)
    path = runtime.root / managed_root.replace('\\', '/')
    path.mkdir(parents=True, exist_ok=True)
    (path / 'bad.md').write_text(block('BAD', deps=['MISSING']), encoding='utf-8')
    config = runtime.root / 'specalign.yaml'
    config.write_text(yaml.safe_dump({'roots': [managed_root]}), encoding='utf-8')
    subprocess.run(['git', '-C', str(runtime.root), 'add', 'specalign.yaml', str(path)], check=True)
    config.write_text('roots: [', encoding='utf-8')
    report = git_check(runtime.root)
    assert not report['valid']
    assert any(f['code'] == 'missing_target' for f in report['findings'])


def test_modified_codex_handler_is_preserved(project):
    runtime, spec = project
    install(runtime.root, codex=True)
    path = runtime.root / '.codex/hooks.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    value['hooks']['PostToolUse'][0]['hooks'][0]['timeout'] = 99
    path.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ProtocolError):
        install(runtime.root, codex=True)
    uninstall(runtime.root, codex=True)
    remaining = json.loads(path.read_text(encoding='utf-8'))
    assert remaining['hooks']['PostToolUse'][0]['hooks'][0]['timeout'] == 99


def test_inline_mcp_table_rejected_without_mutating_files(project):
    runtime, spec = project
    path = runtime.root / '.codex/config.toml'
    path.parent.mkdir()
    path.write_text('mcp_servers = { other = { command = "other" } }\n', encoding='utf-8')
    original = path.read_bytes()
    with pytest.raises(ProtocolError, match='cannot be extended safely'):
        install(runtime.root, codex=True)
    assert path.read_bytes() == original
    assert not (runtime.root / '.codex/hooks.json').exists()

