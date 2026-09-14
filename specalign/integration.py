"""Project-scoped installation. Never edits trust or authentication settings."""
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from importlib.resources import files
from pathlib import Path

from .config import load_config
from .protocol import ProtocolError

MARKER = 'Spec Align document check'
GIT_MARKER = '# spec-align managed pre-commit v1'
MCP_START = '# SPECALIGN MCP START'
MCP_END = '# SPECALIGN MCP END'


def launch_command(root, operation):
    prefix = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'specalign']
    return [*prefix, '--root', str(root), operation]


def mcp_configuration(root, owned):
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    path = root / '.codex/config.toml'
    content = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    old = owned.get('mcp_block')
    if old:
        if content.count(old) != 1:
            raise ProtocolError('Managed MCP configuration has local edits; preserve and update manually')
        remainder = content.replace(old, '', 1)
    else:
        remainder = content
    try:
        parsed = tomllib.loads(remainder)
    except ValueError as error:
        raise ProtocolError(f'Cannot parse existing Codex config: {error}') from error
    if 'specalign' in parsed.get('mcp_servers', {}):
        raise ProtocolError('Existing specalign MCP entry is not owned by this installer')
    arguments = launch_command(root, 'serve')[1:]
    block = MCP_START + '\n[mcp_servers.specalign]\ncommand = ' + json.dumps(sys.executable, ensure_ascii=False)
    block += '\nargs = ' + json.dumps(arguments, ensure_ascii=False) + '\n' + MCP_END + '\n'
    # Replace in place on upgrade; append only on first installation.
    new = content.replace(old, block, 1) if old else content + ('\n' if content and not content.endswith('\n') else '') + block
    try:
        tomllib.loads(new)
    except ValueError as error:
        raise ProtocolError(f'Existing TOML layout cannot be extended safely; configure MCP manually: {error}') from error
    return path, new, block


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding='utf-8') == text:
        return False
    descriptor, temp = tempfile.mkstemp(prefix='.specalign-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)
    return True


def hooks_file(root):
    path = root / '.codex' / 'hooks.json'
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {'hooks': {}}
    except (ValueError, OSError) as error:
        raise ProtocolError(f'Cannot read existing hooks: {error}') from error
    if not isinstance(value, dict) or not isinstance(value.get('hooks', {}), dict):
        raise ProtocolError('Invalid existing hooks mapping')
    value.setdefault('hooks', {})
    for event, groups in value['hooks'].items():
        if not isinstance(groups, list) or any(not isinstance(g, dict) or not isinstance(g.get('hooks', []), list) for g in groups):
            raise ProtocolError(f'Invalid hook groups for {event}')
    return path, value


def ours(handler):
    return isinstance(handler, dict) and handler.get('statusMessage') == MARKER and 'specalign' in handler.get('command', '')


def strip_handlers(value, owned_handlers):
    for event in list(value['hooks']):
        groups = []
        for group in value['hooks'][event]:
            kept = [h for h in group.get('hooks', []) if h not in owned_handlers]
            if kept or not group.get('hooks'):
                groups.append({**group, 'hooks': kept})
        if groups:
            value['hooks'][event] = groups
        else:
            del value['hooks'][event]


def git_hook_path(root):
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True, encoding='utf-8', timeout=10)
    if result.returncode or Path(result.stdout.strip()).resolve() != root:
        raise ProtocolError('Git hook installation requires this project to be a repository root')
    custom = subprocess.run(['git', '-C', str(root), 'config', '--get', 'core.hooksPath'], capture_output=True, text=True, encoding='utf-8', timeout=10)
    if custom.returncode == 0:
        raise ProtocolError('Custom core.hooksPath configured; install the check there manually')
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--git-path', 'hooks/pre-commit'], capture_output=True, text=True, encoding='utf-8', timeout=10)
    if result.returncode:
        raise ProtocolError('Cannot resolve Git hooks directory')
    path = Path(result.stdout.strip())
    return path if path.is_absolute() else root / path


def install(root, codex=False, git_hook=False):
    config = load_config(root)
    if not all((root / p).is_dir() for p in config['roots']):
        raise ProtocolError('Run init before installing integration')
    changed = []
    ownership = root / '.specalign' / 'integration.json'
    owned = json.loads(ownership.read_text(encoding='utf-8')) if ownership.exists() else {}
    if git_hook:
        git_path = git_hook_path(root)
        if git_path.exists() and hashlib.sha256(git_path.read_bytes()).hexdigest() != owned.get('git_hash'):
            raise ProtocolError('Existing or modified pre-commit preserved; add specalign git-check manually')
    if codex:
        path, value = hooks_file(root)
        mcp_path, mcp_text, mcp_block = mcp_configuration(root, owned)
        old_handlers = owned.get('hook_handlers', [])
        if any(ours(h) and h not in old_handlers for groups in value['hooks'].values() for g in groups for h in g.get('hooks', [])):
            raise ProtocolError('Existing Spec Align hook was modified or is not owned by this install; preserve and update manually')
        strip_handlers(value, old_handlers)
        args = launch_command(root, 'hook')
        command = subprocess.list2cmdline(args) if os.name == 'nt' else shlex.join(args)
        handler = {'type': 'command', 'command': command, 'timeout': 15, 'statusMessage': MARKER}
        if os.name == 'nt':
            handler['commandWindows'] = command
        for event in ('PostToolUse', 'Stop'):
            value['hooks'].setdefault(event, []).append({'hooks': [handler]})
        skill = root / '.agents' / 'skills' / 'spec-align' / 'SKILL.md'
        template = files('specalign').joinpath('assets/SKILL.md').read_text(encoding='utf-8')
        previous = owned.get('skill_hash')
        current = hashlib.sha256(skill.read_bytes()).hexdigest() if skill.exists() else None
        expected = hashlib.sha256(template.encode()).hexdigest()
        if current and current not in {previous, expected}:
            raise ProtocolError('Existing skill has local edits; preserve it and update manually')
        if atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n'):
            changed.append(str(path))
        if atomic_write(skill, template):
            changed.append(str(skill))
        if atomic_write(mcp_path, mcp_text):
            changed.append(str(mcp_path))
        owned.update({'skill_hash': expected, 'hook_handlers': [handler], 'mcp_block': mcp_block})
    if git_hook:
        path = git_path
        command = shlex.join([arg.replace('\\', '/') for arg in launch_command(root, 'git-check')])
        if atomic_write(path, '#!/bin/sh\n' + GIT_MARKER + '\nexec ' + command + '\n'):
            changed.append(str(path))
        path.chmod(path.stat().st_mode | 0o111)
        owned['git_hash'] = hashlib.sha256(path.read_bytes()).hexdigest()
    atomic_write(ownership, json.dumps(owned, ensure_ascii=False, indent=2) + '\n')
    return {'changed': changed, 'trust': 'Review and trust the project and hooks in Codex /hooks; installer does not grant trust.',
            'host_delivery': 'not_verified', 'mcp_command': launch_command(root, 'serve')}


def uninstall(root, codex=False, git_hook=False):
    changed, preserved = [], []
    ownership = root / '.specalign' / 'integration.json'
    owned = json.loads(ownership.read_text(encoding='utf-8')) if ownership.exists() else {}
    if codex:
        path, value = hooks_file(root)
        if path.exists():
            if any(ours(h) and h not in owned.get('hook_handlers', []) for groups in value['hooks'].values() for g in groups for h in g.get('hooks', [])):
                preserved.append(str(path))
            strip_handlers(value, owned.get('hook_handlers', []))
            if atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n'):
                changed.append(str(path))
        skill = root / '.agents' / 'skills' / 'spec-align' / 'SKILL.md'
        if ownership.exists():
            if skill.exists() and hashlib.sha256(skill.read_bytes()).hexdigest() == owned.get('skill_hash'):
                skill.unlink()
                changed.append(str(skill))
            elif skill.exists():
                preserved.append(str(skill))
            owned.pop('skill_hash', None)
            owned.pop('hook_handlers', None)
            mcp_path = root / '.codex/config.toml'
            old = owned.pop('mcp_block', None)
            if old and mcp_path.exists():
                content = mcp_path.read_text(encoding='utf-8')
                if content.count(old) == 1:
                    if atomic_write(mcp_path, content.replace(old, '', 1)):
                        changed.append(str(mcp_path))
                else:
                    preserved.append(str(mcp_path))
    if git_hook:
        path = git_hook_path(root)
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == owned.get('git_hash'):
            path.unlink()
            changed.append(str(path))
        elif path.exists():
            preserved.append(str(path))
        owned.pop('git_hash', None)
    if ownership.exists():
        atomic_write(ownership, json.dumps(owned, ensure_ascii=False, indent=2) + '\n')
    return {'changed': changed, 'preserved': preserved}


def doctor(root):
    path, value = hooks_file(root)
    return {'project': str(root), 'python': sys.executable, 'codex_executable': shutil.which('codex'),
            'managed_roots': load_config(root)['roots'],
            'configured_events': [e for e, groups in value['hooks'].items() if any(ours(h) for g in groups for h in g.get('hooks', []))],
            'hook_file': str(path), 'trust': 'unknown; inspect Codex /hooks', 'host_delivery': 'not_verified'}


def git_check(root):
    """Validate the staged document snapshot, not the working-tree approximation."""
    from .core import Runtime
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '--stage', '-z'], capture_output=True, timeout=15)
    if result.returncode:
        raise ProtocolError('Cannot read Git index')
    with tempfile.TemporaryDirectory(prefix='specalign-index-') as directory:
        temp = Path(directory)
        entries = []
        for entry in result.stdout.split(b'\0'):
            if not entry:
                continue
            metadata, raw_path = entry.split(b'\t', 1)
            mode, object_id, stage = metadata.decode().split()
            name = raw_path.decode('utf-8')
            if stage != '0':
                raise ProtocolError('Resolve index merge conflicts before spec check')
            if name == 'specalign.yaml':
                data = subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', object_id], timeout=10)
                (temp / name).write_bytes(data)
            entries.append((mode, object_id, name))
        # With no staged config, default roots apply (not uncommitted config).
        config = load_config(temp)
        for managed in config['roots']:
            (temp / managed).mkdir(parents=True, exist_ok=True)
        for mode, object_id, name in entries:
            if not name.lower().endswith('.md') or not any(name.startswith(p.rstrip('/') + '/') for p in config['roots']):
                continue
            if mode != '100644' and mode != '100755':
                raise ProtocolError('Staged managed Markdown must be a regular file')
            target = temp / name
            if not target.resolve().is_relative_to(temp):
                raise ProtocolError('Invalid staged document path')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', object_id], timeout=10))
        runtime = Runtime(temp)
        try:
            report = runtime.scan()
            # Review ledger is local and intentionally not in Git; this gate is structural.
            report['findings'] = [f for f in report['findings'] if f['severity'] == 'error']
            report['gate'] = 'staged_structure_only'
            return report
        finally:
            runtime.close()

