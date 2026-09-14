"""Versioned Markdown declaration protocol; no semantic inference."""
import hashlib
import json
import re
import yaml
from markdown_it import MarkdownIt


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class ProtocolError(ValueError):
    pass


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in mapping:
            raise ProtocolError('Metadata keys must be unique strings')
        mapping[key] = loader.construct_object(value_node)
    return mapping


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def parse_document(text, path):
    """Only standalone HTML comment tokens count; fenced examples are ignored."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.splitlines(keepends=True)
    opened = None
    items = []
    for token in MarkdownIt('commonmark').parse(text):
        if token.type != 'html_block':
            continue
        marker = token.content.strip()
        if re.match(r'<!--\s*spec(?:\s|$)', marker):
            if opened is not None or not marker.endswith('-->'):
                raise ProtocolError('Nested or unclosed spec metadata')
            match = re.fullmatch(r'<!-- spec\n(.*?)\n-->', marker, re.S)
            if not match:
                raise ProtocolError('Use a standalone <!-- spec metadata block')
            try:
                meta = yaml.load(match.group(1), Loader=UniqueLoader)
            except yaml.YAMLError as error:
                raise ProtocolError(f'Invalid YAML: {error}') from error
            if not isinstance(meta, dict) or set(meta) - {'id', 'status', 'depends_on', 'references', 'supersedes', 'challenges', 'scope', 'kind'}:
                raise ProtocolError('Unknown metadata fields or invalid mapping')
            if not isinstance(meta.get('id'), str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', meta['id']):
                raise ProtocolError('id must be a stable ASCII identifier')
            if not isinstance(meta.get('status'), str) or meta['status'] not in {'proposed', 'active', 'retired'}:
                raise ProtocolError('status must be proposed, active or retired')
            for name in ('kind', 'scope'):
                if name in meta and (not isinstance(meta[name], str) or not meta[name].strip()):
                    raise ProtocolError(f'{name} must be a nonempty string')
            for relation in ('depends_on', 'references', 'supersedes', 'challenges'):
                if relation in {'supersedes', 'challenges'} and relation not in meta:
                    continue
                values = meta.setdefault(relation, [])
                if not isinstance(values, list) or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', v) for v in values):
                    raise ProtocolError(f'{relation} must be a list of IDs')
                if len(set(values)) != len(values):
                    raise ProtocolError(f'Duplicate {relation}')
                meta[relation] = sorted(values)
            opened = (meta, token.map[0] + 1, token.map[1])
        elif marker.startswith('<!-- /spec'):
            if marker != '<!-- /spec -->' or opened is None:
                raise ProtocolError('Unexpected or malformed spec closing marker')
            meta, start, body_start = opened
            body = ''.join(lines[body_start:token.map[0]]).strip()
            items.append({**meta, 'body': body, 'path': path, 'line': start,
                          'version': digest({'metadata': meta, 'body': body})})
            opened = None
    if opened is not None:
        raise ProtocolError('Missing <!-- /spec -->')
    return items


def finding(code, item, message, severity='error', **extra):
    return {'code': code, 'item': item, 'message': message, 'severity': severity, **extra}

