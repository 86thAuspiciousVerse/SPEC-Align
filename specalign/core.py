"""Transactional document graph and review ledger."""
import difflib
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import deque
from contextlib import closing, contextmanager
from pathlib import Path
import yaml

from .protocol import ProtocolError, digest, finding, parse_document
from .config import excluded, load_config
from .graph import cycle_members, edges, impact, mermaid
from .output import agent_report


class Runtime:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config = load_config(self.root)
        if not all((self.root / p).is_dir() for p in self.config['roots']):
            raise ProtocolError('Missing managed directory; run init or check configured roots')
        state = self.root / '.specalign'
        state.mkdir(exist_ok=True)
        self.db = sqlite3.connect(state / 'state.sqlite3', timeout=10, isolation_level=None)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reviews (
                seq INTEGER PRIMARY KEY, item TEXT NOT NULL, basis TEXT NOT NULL,
                snapshot TEXT NOT NULL, reason TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE INDEX IF NOT EXISTS review_basis ON reviews(item,basis);
            CREATE TABLE IF NOT EXISTS review_batches (batch TEXT NOT NULL, review_seq INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS deliveries (
                session TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, checks INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS file_cache (path TEXT PRIMARY KEY, hash TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS issues (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP, last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                occurrences INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS issue_events (
                seq INTEGER PRIMARY KEY, issue TEXT NOT NULL, status TEXT NOT NULL,
                snapshot TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS actions (
                seq INTEGER PRIMARY KEY, item TEXT NOT NULL, action TEXT NOT NULL,
                reason TEXT NOT NULL, actor TEXT NOT NULL, snapshot TEXT NOT NULL,
                created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY, item TEXT, action TEXT, reason TEXT, actor TEXT,
                snapshot TEXT, status TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        with self.transaction():
            version = self.db.execute("SELECT value FROM state WHERE key='parser_version'").fetchone()
            if not version or version[0] != '2':
                self.db.execute('DELETE FROM file_cache')
                self.db.execute("INSERT OR REPLACE INTO state VALUES ('parser_version','2')")

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def _collect(self):
        items, errors, files, unmanaged = {}, [], {}, []
        self.config = load_config(self.root)
        self.stats = {'files': 0, 'parsed': 0, 'cached': 0}
        paths = set()
        for directory in self.config['roots']:
            folder = self.root / directory
            if not folder.is_dir() or folder.is_symlink():
                errors.append(finding('scan_error', directory, 'Managed directory missing or symlinked'))
                continue
            paths.update(folder.rglob('*.md'))
        for path in sorted(paths):
            rel = path.relative_to(self.root).as_posix()
            if excluded(rel, self.config['exclude']):
                continue
            try:
                if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                    raise ProtocolError('Symlinks/out-of-root documents are not supported')
                raw = path.read_bytes()
                if len(raw) > 2_000_000:
                    raise ProtocolError('Managed Markdown exceeds the 2 MB per-file limit')
                files[rel] = hashlib.sha256(raw).hexdigest()
                self.stats['files'] += 1
                cached = self.db.execute('SELECT hash,payload FROM file_cache WHERE path=?', (rel,)).fetchone()
                if cached and cached[0] == files[rel]:
                    parsed = json.loads(cached[1])
                    self.stats['cached'] += 1
                else:
                    parsed = parse_document(raw.decode('utf-8-sig'), rel)
                    self.stats['parsed'] += 1
                    self.db.execute('INSERT OR REPLACE INTO file_cache VALUES (?,?,?)',
                                    (rel, files[rel], json.dumps(parsed, ensure_ascii=False)))
                if not parsed:
                    unmanaged.append(rel)
                for item in parsed:
                    if item['id'] in items:
                        errors.append(finding('duplicate_id', item['id'], 'ID occurs more than once', path=rel))
                    else:
                        items[item['id']] = item
            except (OSError, UnicodeError, ValueError) as error:
                errors.append(finding('parse_error', rel, str(error), path=rel))
        self.observed_files = files
        return items, errors, files, unmanaged

    def _publish_report(self, report):
        report['schema_version'] = 1
        report['stats'] = self.stats
        open_ids = set()
        for issue in report['findings']:
            issue['id'] = 'F-' + digest({k: issue.get(k) for k in ('code', 'item', 'target', 'path', 'relation')})[:20]
            if issue['item'] in report['items']:
                issue.setdefault('path', report['items'][issue['item']]['path'])
                issue.setdefault('line', report['items'][issue['item']]['line'])
            ident = issue['id']
            open_ids.add(ident)
            old = self.db.execute('SELECT status FROM issues WHERE id=?', (ident,)).fetchone()
            if not old:
                self.db.execute('INSERT INTO issues(id,payload,status) VALUES (?,?,?)', (ident, json.dumps(issue), 'open'))
            else:
                self.db.execute("UPDATE issues SET payload=?,status='open',last_seen=CURRENT_TIMESTAMP,occurrences=occurrences+? WHERE id=?",
                                (json.dumps(issue), int(old[0] == 'resolved'), ident))
            if not old or old[0] == 'resolved':
                self.db.execute('INSERT INTO issue_events(issue,status,snapshot) VALUES (?,?,?)', (ident, 'open', report['snapshot']))
        # A parse failure must not resolve issues merely because their graph is unavailable.
        if report['snapshot'] is not None:
            for ident, in self.db.execute("SELECT id FROM issues WHERE status='open'").fetchall():
                if ident not in open_ids:
                    self.db.execute("UPDATE issues SET status='resolved',last_seen=CURRENT_TIMESTAMP WHERE id=?", (ident,))
                    self.db.execute('INSERT INTO issue_events(issue,status,snapshot) VALUES (?,?,?)', (ident, 'resolved', report['snapshot']))
        self.db.execute("INSERT OR REPLACE INTO state VALUES ('report',?)", (json.dumps(report, ensure_ascii=False),))
        return report

    @staticmethod
    def basis(item, items):
        return digest({'item': item['version'], 'dependencies': {
            dep: items[dep]['version'] for dep in item['depends_on'] if dep in items}})

    def _scan(self):
        items, errors, files, unmanaged = self._collect()
        if errors:
            previous = self.db.execute("SELECT value FROM state WHERE key='current'").fetchone()
            return self._publish_report({'snapshot': None, 'last_valid_snapshot': previous[0] if previous else None,
                    'findings': errors, 'items': {}, 'unmanaged': unmanaged, 'valid': False})
        snapshot = digest({'items': items, 'files': files, 'config': self.config})
        self.db.execute('INSERT OR IGNORE INTO snapshots VALUES (?,?)', (snapshot, json.dumps(items, ensure_ascii=False)))
        self.db.execute("INSERT OR REPLACE INTO state VALUES ('current',?)", (snapshot,))
        findings, direct_stale = [], set()
        reverse = {}
        replacements = {}
        for ident, item in items.items():
            if item['status'] != 'proposed':
                for target in item.get('supersedes', []):
                    replacements.setdefault(target, []).append(ident)
        for target, successors in sorted(replacements.items()):
            if len(successors) > 1:
                findings.append(finding('multiple_successors', target, 'More than one adopted successor', successors=sorted(successors)))
        for ident, item in items.items():
            item['effective_status'] = 'superseded' if ident in replacements else item['status']
        for ident, item in sorted(items.items()):
            for relation in ('depends_on', 'references', 'supersedes', 'challenges'):
                for dep in item.get(relation, []):
                    if dep not in items:
                        findings.append(finding('missing_target', ident, f'{relation} target {dep} is missing', target=dep, relation=relation))
                    elif relation == 'depends_on':
                        reverse.setdefault(dep, []).append(ident)
                        if item['effective_status'] == 'active' and items[dep]['effective_status'] != 'active':
                            findings.append(finding('inactive_dependency', ident, f'{dep} is not active', target=dep))
                    elif relation == 'supersedes':
                        if dep == ident or items[dep].get('scope', 'project') != item.get('scope', 'project'):
                            findings.append(finding('invalid_replacement', ident, 'Replacement must target a different item in the same scope', target=dep))
                    elif relation == 'challenges' and item['effective_status'] != 'retired' and items[dep]['effective_status'] == 'active':
                        findings.append(finding('open_challenge', ident, 'Explicit challenge requires a decision', 'warning', target=dep))
            if item['effective_status'] == 'active' and item['depends_on']:
                reviewed = self.db.execute('SELECT 1 FROM reviews WHERE item=? AND basis=?',
                                           (ident, self.basis(item, items))).fetchone()
                if not reviewed:
                    direct_stale.add(ident)
                    findings.append(finding('needs_review', ident, 'Current content and dependencies lack a matching review', 'warning'))
        for relation in ('depends_on', 'supersedes'):
            for ident in sorted(cycle_members(items, relation)):
                findings.append(finding('dependency_cycle' if relation == 'depends_on' else 'replacement_cycle', ident,
                                        f'Cycle in {relation}'))
        queue = deque((ident, [ident]) for ident in sorted(direct_stale))
        reached = set(direct_stale)
        while queue:
            parent, chain = queue.popleft()
            for child in sorted(reverse.get(parent, [])):
                if child in reached or items[child]['effective_status'] != 'active':
                    continue
                reached.add(child)
                child_chain = [child, *chain]
                findings.append(finding('upstream_pending', child, 'An upstream review is unresolved', 'warning', chain=child_chain))
                queue.append((child, child_chain))
        return self._publish_report({'snapshot': snapshot, 'findings': findings, 'items': items, 'unmanaged': unmanaged,
                'valid': not any(f['severity'] == 'error' for f in findings)})

    def scan(self):
        with self.transaction():
            report = self._scan()
            self.db.execute("INSERT OR REPLACE INTO state VALUES ('report',?)", (json.dumps(report, ensure_ascii=False),))
            return report

    def review(self, ident, snapshot, reason):
        if not reason.strip():
            raise ProtocolError('A review reason is required')
        with self.transaction():
            report = self._scan()
            if not report['valid'] or report['snapshot'] != snapshot:
                raise ProtocolError('Snapshot changed or structure invalid; scan and review the current evidence')
            item = report['items'].get(ident)
            if not item or item.get('effective_status', item['status']) != 'active':
                raise ProtocolError('Review target must be an active item')
            # A second content scan catches changes during the evidence read. External
            # editors cannot be locked; edits after this point are caught next scan.
            if self._scan()['snapshot'] != snapshot:
                raise ProtocolError('Files changed during review; inspect a new snapshot')
            self.db.execute('INSERT INTO reviews(item,basis,snapshot,reason) VALUES (?,?,?,?)',
                            (ident, self.basis(item, report['items']), snapshot, reason))
        return self.scan()

    def check(self, detail='summary', scope=None, since_snapshot=None, limit=20):
        from .query import check
        return check(self, detail, scope, since_snapshot, limit)

    def context_many(self, ids, max_chars=12000, related=False, max_items=30):
        from .query import context_many
        return context_many(self, ids, max_chars, related, max_items)

    def migration_plan(self, scope=None):
        from .query import migration_plan
        return migration_plan(self, scope)

    def review_batch(self, snapshot, reviews):
        if not isinstance(reviews, list) or not 1 <= len(reviews) <= 200:
            raise ProtocolError('reviews must contain 1..200 entries')
        seen = set()
        for entry in reviews:
            if not isinstance(entry, dict) or set(entry) != {'item', 'reason'}:
                raise ProtocolError('Each review requires only item and reason')
            if not isinstance(entry['item'], str) or not isinstance(entry['reason'], str) or not entry['reason'].strip() or entry['item'] in seen:
                raise ProtocolError('Unique items and nonempty reasons required')
            seen.add(entry['item'])
        import uuid
        batch = uuid.uuid4().hex
        with self.transaction():
            report = self._scan()
            if not report['valid'] or report['snapshot'] != snapshot:
                raise ProtocolError('Snapshot changed or structure invalid')
            for entry in reviews:
                item = report['items'].get(entry['item'])
                if not item or item.get('effective_status', item['status']) != 'active':
                    raise ProtocolError('Every review target must be active')
            for entry in reviews:
                item = report['items'][entry['item']]
                cursor = self.db.execute('INSERT INTO reviews(item,basis,snapshot,reason) VALUES (?,?,?,?)',
                    (entry['item'], self.basis(item, report['items']), snapshot, entry['reason']))
                self.db.execute('INSERT INTO review_batches(batch,review_seq) VALUES (?,?)', (batch, cursor.lastrowid))
            after = self._scan()
            if not after['valid'] or after['snapshot'] != snapshot:
                raise ProtocolError('Files changed during batch; no reviews saved')
        from .query import project_report
        return {**project_report(after), 'batch_id': batch, 'reviewed_ids': sorted(seen)}

    def history(self, ident=None):
        self.scan()
        reviews = self.db.execute('SELECT seq,item,basis,snapshot,reason,created FROM reviews' +
                                  (' WHERE item=?' if ident else '') + ' ORDER BY seq', (ident,) if ident else ()).fetchall()
        issues = []
        for row in self.db.execute('SELECT id,payload,status,first_seen,last_seen,occurrences FROM issues ORDER BY id'):
            payload = json.loads(row[1])
            if ident is None or payload['item'] == ident:
                events = self.db.execute('SELECT status,snapshot,created FROM issue_events WHERE issue=? ORDER BY seq', (row[0],)).fetchall()
                issues.append({**payload, 'status': row[2], 'first_seen': row[3], 'last_seen': row[4], 'occurrences': row[5],
                               'events': [dict(zip(('status', 'snapshot', 'created'), event)) for event in events]})
        actions = self.db.execute('SELECT seq,item,action,reason,actor,snapshot,created FROM actions' +
                                  (' WHERE item=?' if ident else '') + ' ORDER BY seq', (ident,) if ident else ()).fetchall()
        pending = self.db.execute("SELECT id,item,action,status FROM operations WHERE status='pending'").fetchall()
        return {'schema_version': 1, 'pending_operations': [dict(zip(('id','item','action','status'), row)) for row in pending],
                'reviews': [dict(zip(('sequence', 'item', 'basis', 'snapshot', 'reason', 'created'), row)) for row in reviews],
                'batches': [dict(zip(('batch_id', 'review_sequence'), row)) for row in self.db.execute('SELECT b.batch,b.review_seq FROM review_batches b JOIN reviews r ON r.seq=b.review_seq' + (' WHERE r.item=?' if ident else '') + ' ORDER BY b.review_seq', (ident,) if ident else ())],
                  'issues': issues, 'actions': [dict(zip(('sequence', 'item', 'action', 'reason', 'actor', 'snapshot', 'created'), row)) for row in actions]}

    def backup(self, destination):
        destination = Path(destination).resolve()
        if destination.exists():
            raise ProtocolError('Backup destination already exists; choose a new file')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(destination)) as copy:
            self.db.backup(copy)
        return {'backup': str(destination)}

    def transition(self, ident, action, snapshot, reason, actor):
        if action not in {'accept', 'retire'} or not reason.strip() or not actor.strip():
            raise ProtocolError('accept/retire requires a reason and actor')
        with self.transaction():
            report = self._scan()
            if not report['valid'] or report['snapshot'] != snapshot:
                raise ProtocolError('Snapshot changed or invalid; inspect current evidence')
            item = report['items'].get(ident)
            if not item or (action == 'accept' and item['status'] != 'proposed') or (action == 'retire' and item['status'] != 'active'):
                raise ProtocolError('Invalid lifecycle transition')
            if action == 'accept':
                targets = set(item.get('supersedes', []))
                if targets.intersection(item['depends_on']):
                    raise ProtocolError('An adopted item cannot depend on an item it supersedes')
                for key, other in report['items'].items():
                    if key != ident and other['status'] != 'proposed' and targets.intersection(other.get('supersedes', [])):
                        raise ProtocolError('Another adopted item already supersedes this target')
                if any(report['items'][dep]['effective_status'] != 'active' for dep in item['depends_on']):
                    raise ProtocolError('Cannot adopt an item with inactive dependencies')
            cursor = self.db.execute('INSERT INTO operations(item,action,reason,actor,snapshot,status) VALUES (?,?,?,?,?,?)',
                                     (ident, action, reason, actor, snapshot, 'pending'))
            operation = cursor.lastrowid
        temporary = None
        replaced = False
        try:
            with self.transaction():
                if self._scan()['snapshot'] != snapshot:
                    raise ProtocolError('Snapshot changed before applying decision')
                path = self.root / item['path']
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != self.observed_files[item['path']]:
                    raise ProtocolError('File changed before applying decision')
                lines = raw.decode('utf-8-sig').replace('\r\n', '\n').splitlines(keepends=True)
                start = item['line'] - 1
                end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == '-->')
                meta = {key: item[key] for key in ('id','status','depends_on','references','supersedes','challenges','scope','kind') if key in item}
                meta['status'] = 'active' if action == 'accept' else 'retired'
                header = '<!-- spec\n' + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + '-->\n'
                content = ''.join(lines[:start]) + header + ''.join(lines[end + 1:])
                descriptor, temporary = tempfile.mkstemp(prefix='.specalign-', dir=path.parent)
                with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                if path.read_bytes() != raw:
                    raise ProtocolError('File changed during decision; retry after inspection')
                os.replace(temporary, path)
                replaced = True
                after = self._scan()
                self.db.execute('INSERT INTO actions(item,action,reason,actor,snapshot) VALUES (?,?,?,?,?)',
                                (ident, action, reason, actor, after['snapshot']))
                self.db.execute("UPDATE operations SET status='applied' WHERE id=?", (operation,))
            return after
        except BaseException:
            if not replaced:
                with self.transaction():
                    self.db.execute("UPDATE operations SET status='failed' WHERE id=?", (operation,))
            # If file replacement succeeded but DB commit did not, keep pending
            # intent for audit/recovery; never silently rewrite the user's file.
            raise
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)

    def explain(self, ident):
        """Return current evidence and a reviewed baseline without approving it."""
        with self.transaction():
            report = self._scan()
            item = report['items'].get(ident)
            if item is None:
                raise ProtocolError('Item unavailable; run check to inspect missing IDs or parse errors')
            basis = self.basis(item, report['items'])
            # Prefer an applicable review (including after a revert), otherwise
            # show the latest review so an agent can inspect what changed.
            row = self.db.execute('''
                SELECT seq,basis,snapshot,reason,created FROM reviews
                WHERE item=? ORDER BY (basis=?) DESC,seq DESC LIMIT 1
            ''', (ident, basis)).fetchone()
            previous, review = {}, None
            if row:
                stored = self.db.execute('SELECT payload FROM snapshots WHERE id=?', (row[2],)).fetchone()
                if stored is None:
                    raise ProtocolError('Review baseline snapshot is missing; restore the audit database')
                previous = json.loads(stored[0])
                review = {'sequence': row[0], 'snapshot': row[2], 'reason': row[3],
                          'created': row[4], 'matches_current_basis': row[1] == basis}
            old_item = previous.get(ident)
            related = sorted({ident, *item['depends_on'], *(old_item or {}).get('depends_on', [])})

            def content(record):
                if record is None:
                    return ''
                fields = {key: record[key] for key in ('id', 'status', 'depends_on', 'references', 'supersedes', 'challenges', 'scope', 'kind', 'body') if key in record}
                return json.dumps(fields, ensure_ascii=False, indent=2, sort_keys=True) + '\n'

            changes = []
            for key in related:
                before, after = previous.get(key), report['items'].get(key)
                if not row or content(before) != content(after):
                    changes.append({'item': key, 'before': before, 'after': after,
                                    'diff': ''.join(difflib.unified_diff(
                                        content(before).splitlines(keepends=True),
                                        content(after).splitlines(keepends=True),
                                        fromfile=f'reviewed/{key}', tofile=f'current/{key}'))})
            return {'snapshot': report['snapshot'], 'valid': report['valid'], 'item': item,
                    'dependencies': {key: report['items'].get(key) for key in item['depends_on']},
                    'review': review, 'changes': changes,
                    'findings': [f for f in report['findings'] if f['item'] == ident],
                    'project_error_count': sum(f['severity'] == 'error' for f in report['findings'])}

    def context(self, ident, max_chars=12000):
        if type(max_chars) is not int or not 500 <= max_chars <= 100000:
            raise ProtocolError('max_chars must be between 500 and 100000')
        report = self.scan()
        if ident not in report['items']:
            raise ProtocolError('Context target unavailable; inspect check')
        wanted, queue = [], deque([ident])
        seen = set()
        while queue:
            key = queue.popleft()
            if key in seen or key not in report['items']:
                continue
            seen.add(key)
            wanted.append(key)
            queue.extend(report['items'][key]['depends_on'])
        selected, remaining, omitted = {}, max_chars, []
        for key in wanted:
            item = dict(report['items'][key])
            body = item['body']
            if remaining <= 0:
                omitted.append(key)
                continue
            item['body'] = body[:remaining]
            item['body_truncated'] = len(item['body']) < len(body)
            remaining -= len(item['body'])
            selected[key] = item
        return {'schema_version': 1, 'snapshot': report['snapshot'], 'valid': report['valid'],
                'target': ident, 'items': selected, 'omitted_items': omitted,
                'body_character_budget': max_chars,
                'findings': [f for f in report['findings'] if f['item'] in seen],
                'project_error_count': sum(f['severity'] == 'error' for f in report['findings'])}

    def graph(self, ident=None, format='json'):
        report = self.scan()
        if ident is not None and ident not in report['items']:
            raise ProtocolError('Impact target unavailable; inspect check')
        if format == 'mermaid':
            return mermaid(report['items'])
        graph_edges = edges(report['items'])
        result = {'schema_version': 1, 'snapshot': report['snapshot'], 'valid': report['valid'],
                  'nodes': report['items'], 'edges': graph_edges, 'findings': report['findings']}
        if ident:
            chains = impact(report['items'], ident)
            result['impact'] = [{'item': key, 'chain': chain, 'direct': len(chain) == 2} for key, chain in sorted(chains.items())]
        return result

    def hook(self, event):
        if not isinstance(event, dict):
            raise ProtocolError('Hook input must be a JSON object')
        if not isinstance(event.get('hook_event_name'), str):
            raise ProtocolError('hook_event_name must be a string')
        if 'stop_hook_active' in event and type(event['stop_hook_active']) is not bool:
            raise ProtocolError('stop_hook_active must be boolean')
        if event.get('hook_event_name') not in {'PostToolUse', 'Stop'}:
            return {}
        with self.transaction():
            report = self._scan()
            self.db.execute("INSERT OR REPLACE INTO state VALUES ('report',?)", (json.dumps(report, ensure_ascii=False),))
            related = set()
            for problem in report['findings']:
                related.update([problem['item'], problem.get('target'), *problem.get('chain', [])])
            for ident in list(related):
                if ident in report['items']:
                    related.update(report['items'][ident]['depends_on'])
            versions = {ident: report['items'][ident]['version']
                        for ident in related if ident in report['items']}
            fingerprint = digest({'versions': versions, 'findings': report['findings']})
            session = str(event.get('session_id', 'unknown')) + ':' + event['hook_event_name']
            old = self.db.execute('SELECT fingerprint,checks FROM deliveries WHERE session=?', (session,)).fetchone()
            count = old[1] + 1 if old and old[0] == fingerprint else 0
            notify = bool(report['findings']) and (count == 0 or count >= self.config['remind_after'])
            self.db.execute('INSERT OR REPLACE INTO deliveries VALUES (?,?,?)', (session, fingerprint, 0 if notify else count))
        if event['hook_event_name'] == 'Stop' and self.config['stop_on_errors'] and not report['valid'] and not event.get('stop_hook_active', False):
            return {'decision': 'block', 'reason': agent_report(report, self.root)}
        if not notify:
            return {}
        message = agent_report(report, self.root, limit=8)
        if event['hook_event_name'] == 'Stop':
            # Advisory only in v0.1. Never create an automatic continuation loop.
            return {'systemMessage': message}
        return {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': message}}

