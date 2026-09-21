"""Small explicit project configuration. No executable configuration."""
import fnmatch
from pathlib import Path

import yaml

from .protocol import ProtocolError, UniqueLoader

DEFAULT = {'version': 1, 'roots': ['spec'], 'exclude': [], 'remind_after': 8, 'stop_on_errors': False}


def initialize_project(root):
    """Create the default project configuration and managed directories."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    config = load_config(root)
    created = []
    for relative in config['roots']:
        path = root / relative
        if not path.exists():
            path.mkdir(parents=True)
            created.append(str(path))
        elif not path.is_dir():
            raise ProtocolError(f'Managed root is not a directory: {path}')
    config_path = root / 'specalign.yaml'
    if not config_path.exists():
        config_path.write_text(yaml.safe_dump(DEFAULT, sort_keys=False), encoding='utf-8')
        created.append(str(config_path))
    return {'project_root': str(root), 'config': str(config_path), 'roots': config['roots'], 'created': created}


def load_config(root):
    # Resolve the project root once before comparing descendants.  On Windows,
    # tempfile paths can use an 8.3 alias while Path.resolve() returns the long
    # form; comparing one resolved path with one unresolved path falsely looks
    # like an out-of-root directory.
    root = Path(root).resolve()
    path = root / 'specalign.yaml'
    try:
        supplied = yaml.load(path.read_text(encoding='utf-8-sig'), Loader=UniqueLoader) if path.exists() else {}
    except (yaml.YAMLError, OSError) as error:
        raise ProtocolError(f'Cannot read specalign.yaml: {error}') from error
    if not isinstance(supplied, dict) or set(supplied) - set(DEFAULT):
        raise ProtocolError('Unknown configuration key or invalid mapping')
    config = {**DEFAULT, **supplied}
    if type(config['version']) is not int or config['version'] != 1:
        raise ProtocolError('Only configuration version 1 is supported')
    for key in ('roots', 'exclude'):
        if not isinstance(config[key], list) or any(not isinstance(v, str) or not v for v in config[key]):
            raise ProtocolError(f'{key} must be a list of nonempty strings')
    if not config['roots'] or len(set(config['roots'])) != len(config['roots']):
        raise ProtocolError('roots must be nonempty and unique')
    config['roots'] = [Path(p.replace('\\', '/')).as_posix() for p in config['roots']]
    if len(set(config['roots'])) != len(config['roots']):
        raise ProtocolError('roots resolve to duplicate directories')
    for value in config['roots']:
        candidate = root / value
        if Path(value).is_absolute() or '..' in Path(value).parts or not candidate.resolve().is_relative_to(root):
            raise ProtocolError('Managed roots must stay within the project')
        if any(part.startswith('.') for part in Path(value).parts if part != '.') or value in {'.', ''}:
            raise ProtocolError('Use explicit document directories, not project or hidden state roots')
    if type(config['remind_after']) is not int or not 1 <= config['remind_after'] <= 1000:
        raise ProtocolError('remind_after must be an integer from 1 to 1000')
    if type(config['stop_on_errors']) is not bool:
        raise ProtocolError('stop_on_errors must be boolean')
    return config


def excluded(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)

