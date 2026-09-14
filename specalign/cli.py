import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .core import ProtocolError, Runtime
from .config import DEFAULT, load_config
from .output import agent_report


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(prog='specalign')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    for name in ('scan', 'check'):
        command = sub.add_parser(name)
        command.add_argument('--agent', action='store_true')
        command.add_argument('--detail', choices=('summary', 'full'), default='full')
        command.add_argument('--scope')
        command.add_argument('--since-snapshot')
        command.add_argument('--limit', type=int, default=20)
        command.add_argument('--fail-on', choices=('warning', 'error'), default='warning')
    context = sub.add_parser('context')
    context.add_argument('items', nargs='+')
    context.add_argument('--related', action='store_true')
    context.add_argument('--max-items', type=int, default=30)
    context.add_argument('--max-chars', type=int, default=12000)
    sub.add_parser('impact').add_argument('item')
    graph = sub.add_parser('graph')
    graph.add_argument('--format', choices=('json', 'mermaid'), default='json')
    sub.add_parser('history').add_argument('item', nargs='?')
    sub.add_parser('backup').add_argument('destination', type=Path)
    sub.add_parser('restore').add_argument('source', type=Path)
    for name in ('accept', 'retire'):
        command = sub.add_parser(name)
        command.add_argument('item')
        command.add_argument('--snapshot', required=True)
        command.add_argument('--reason', required=True)
        command.add_argument('--actor', required=True)
    explain = sub.add_parser('explain')
    explain.add_argument('item')
    review = sub.add_parser('review')
    review.add_argument('item')
    review.add_argument('--snapshot', required=True)
    review.add_argument('--reason', required=True)
    batch = sub.add_parser('review-batch')
    batch.add_argument('--snapshot', required=True)
    batch.add_argument('--file', type=Path, required=True)
    sub.add_parser('migration-plan').add_argument('--scope')
    sub.add_parser('hook')
    sub.add_parser('serve')
    for name in ('install', 'uninstall'):
        command = sub.add_parser(name)
        command.add_argument('--codex', action='store_true')
        command.add_argument('--git-hook', action='store_true')
    sub.add_parser('doctor')
    sub.add_parser('git-check')
    args = parser.parse_args()
    args.root = args.root.resolve()
    runtime = None
    try:
        if args.command == 'init':
            args.root.mkdir(parents=True, exist_ok=True)
            config = load_config(args.root)
            for path in config['roots']:
                (args.root / path).mkdir(parents=True, exist_ok=True)
            config_path = args.root / 'specalign.yaml'
            if not config_path.exists():
                import yaml
                config_path.write_text(yaml.safe_dump(DEFAULT, sort_keys=False), encoding='utf-8')
            print('Initialized managed directories and specalign.yaml; no hooks installed.')
            return 0
        if args.command == 'restore':
            from .storage import restore
            print(json.dumps(restore(args.root, args.source), ensure_ascii=False))
            return 0
        if args.command in {'install', 'uninstall', 'doctor'}:
            from .integration import doctor, install, uninstall
            if args.command == 'doctor':
                result = doctor(args.root)
            else:
                if not args.codex and not args.git_hook:
                    raise ProtocolError('Select --codex and/or --git-hook explicitly')
                result = (install if args.command == 'install' else uninstall)(args.root, args.codex, args.git_hook)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == 'serve':
            from .mcp_server import run_server
            run_server(args.root)
            return 0
        if args.command == 'git-check':
            from .integration import git_check
            result = git_check(args.root)
            print(agent_report(result, args.root))
            return 0 if result['valid'] else 2
        runtime = Runtime(args.root)
        if args.command == 'hook':
            result = runtime.hook(json.load(sys.stdin))
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command == 'review-batch':
            result = runtime.review_batch(args.snapshot, json.loads(args.file.read_text(encoding='utf-8')))
        elif args.command == 'migration-plan':
            result = runtime.migration_plan(args.scope)
        elif args.command == 'review':
            result = runtime.review(args.item, args.snapshot, args.reason)
        elif args.command in {'accept', 'retire'}:
            result = runtime.transition(args.item, args.command, args.snapshot, args.reason, args.actor)
        elif args.command == 'explain':
            result = runtime.explain(args.item)
        elif args.command == 'context':
            result = runtime.context_many(args.items, args.max_chars, args.related, args.max_items)
        elif args.command in {'graph', 'impact'}:
            result = runtime.graph(getattr(args, 'item', None), getattr(args, 'format', 'json'))
        elif args.command == 'history':
            result = runtime.history(args.item)
        elif args.command == 'backup':
            result = runtime.backup(args.destination)
        else:
            result = runtime.check(args.detail, args.scope, args.since_snapshot, args.limit)
        if isinstance(result, str):
            print(result, end='')
            return 0
        if getattr(args, 'agent', False):
            print(agent_report(result, args.root))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        failed = (getattr(args, 'fail_on', 'warning') == 'warning' and result.get('project_unresolved_count', 0) > 0) or any(getattr(args, 'fail_on', 'warning') == 'warning' or f['severity'] == 'error' for f in result.get('findings', []))
        return 2 if failed or result.get('valid') is False else 0
    except (ProtocolError, OSError, sqlite3.Error, ValueError) as error:
        if args.command == 'hook':
            print(json.dumps({'systemMessage': f'Spec Align scan failed: {error}'}, ensure_ascii=False))
            return 0
        print(str(error), file=sys.stderr)
        return 3
    finally:
        if runtime:
            runtime.close()

