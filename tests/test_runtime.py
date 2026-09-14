import json
import subprocess
import sys

import pytest

from specalign.core import ProtocolError, Runtime, parse_document


def block(ident, body='Text', deps=(), refs=()):
    return '<!-- spec\n' + f'id: {ident}\nstatus: active\ndepends_on: {json.dumps(list(deps))}\nreferences: {json.dumps(list(refs))}\n' + '-->\n\n' + body + '\n\n<!-- /spec -->\n'


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'spec').mkdir()
    runtime = Runtime(tmp_path)
    yield runtime, tmp_path / 'spec'
    runtime.close()


def codes(report):
    return {(f['code'], f['item']) for f in report['findings']}


def test_markdown_examples_and_boundaries():
    document = '```markdown\n' + block('EXAMPLE') + '```\n\n' + block('REAL')
    assert [i['id'] for i in parse_document(document, 'x.md')] == ['REAL']
    with pytest.raises(ProtocolError):
        parse_document(block('A').replace('<!-- /spec -->', ''), 'x.md')
    with pytest.raises(ProtocolError):
        parse_document(block('A').replace('id: A', 'id: A\nid: B'), 'x.md')


def test_review_change_and_indirect_propagation(project):
    runtime, spec = project
    (spec / 'a.md').write_text(block('A'), encoding='utf-8')
    (spec / 'b.md').write_text(block('B', deps=['A']), encoding='utf-8')
    (spec / 'c.md').write_text(block('C', deps=['B']), encoding='utf-8')
    report = runtime.scan()
    assert ('needs_review', 'B') in codes(report)
    runtime.review('B', report['snapshot'], 'Initial inspection')
    runtime.review('C', report['snapshot'], 'Initial inspection')
    assert not runtime.scan()['findings']
    (spec / 'a.md').write_text(block('A', 'Changed contract'), encoding='utf-8')
    report = runtime.scan()
    assert codes(report) == {('needs_review', 'B'), ('upstream_pending', 'C')}
    assert not runtime.review('B', report['snapshot'], 'Still compatible')['findings']


def test_snapshot_race_and_self_change(project):
    runtime, spec = project
    file = spec / 'all.md'
    file.write_text(block('A') + '\n' + block('B', deps=['A']), encoding='utf-8')
    old = runtime.scan()['snapshot']
    file.write_text(block('A') + '\n' + block('B', 'New content', ['A']), encoding='utf-8')
    with pytest.raises(ProtocolError, match='Snapshot changed'):
        runtime.review('B', old, 'Old observation')
    current = runtime.scan()
    runtime.review('B', current['snapshot'], 'Reviewed current content')
    file.write_text(block('A') + '\n' + block('B', 'Another edit', ['A']), encoding='utf-8')
    assert ('needs_review', 'B') in codes(runtime.scan())


def test_move_delete_and_restore(project):
    runtime, spec = project
    (spec / 'a.md').write_text(block('A'), encoding='utf-8')
    (spec / 'b.md').write_text(block('B', deps=['A']), encoding='utf-8')
    runtime.review('B', runtime.scan()['snapshot'], 'Checked')
    (spec / 'a.md').rename(spec / 'moved.md')
    assert not runtime.scan()['findings']
    (spec / 'moved.md').unlink()
    report = runtime.scan()
    assert ('missing_target', 'B') in codes(report)
    assert report['items']['B']['depends_on'] == ['A']


def test_parse_failure_preserves_snapshot_and_duplicate_blocks(project):
    runtime, spec = project
    file = spec / 'a.md'
    file.write_text(block('A'), encoding='utf-8')
    previous = runtime.scan()['snapshot']
    file.write_text('<!-- spec\nid: A\n', encoding='utf-8')
    report = runtime.scan()
    assert not report['valid']
    assert report['last_valid_snapshot'] == previous
    assert runtime.db.execute('SELECT payload FROM snapshots WHERE id=?', (previous,)).fetchone()
    file.write_text(block('A') + '\n' + block('A'), encoding='utf-8')
    assert ('duplicate_id', 'A') in codes(runtime.scan())


def test_references_do_not_propagate_and_dependency_cycle(project):
    runtime, spec = project
    file = spec / 'a.md'
    file.write_text(block('A', refs=['B']) + '\n' + block('B', refs=['A']), encoding='utf-8')
    assert not runtime.scan()['findings']
    file.write_text(block('A', deps=['B']) + '\n' + block('B', deps=['A']), encoding='utf-8')
    assert ('dependency_cycle', 'A') in codes(runtime.scan())


def test_hook_dedup_and_unmanaged(project):
    runtime, spec = project
    (spec / 'ordinary.md').write_text('# Background only', encoding='utf-8')
    event = {'hook_event_name': 'PostToolUse', 'session_id': 'test'}
    assert runtime.hook(event) == {}
    assert runtime.scan()['unmanaged'] == ['spec/ordinary.md']
    (spec / 'a.md').write_text(block('B', deps=['MISSING']), encoding='utf-8')
    assert 'additionalContext' in runtime.hook(event)['hookSpecificOutput']
    assert runtime.hook(event) == {}
    for _ in range(6):
        assert runtime.hook(event) == {}
    assert runtime.hook(event)
    runtime.close()
    runtime.db = Runtime(runtime.root).db
    assert runtime.hook(event) == {}


def test_cli_hook_output(project):
    runtime, spec = project
    (spec / 'a.md').write_text(block('B', deps=['MISSING']), encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'specalign', '--root', str(runtime.root), 'hook'],
                            input=json.dumps({'hook_event_name': 'PostToolUse', 'session_id': 'cli'}),
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)['hookSpecificOutput']['hookEventName'] == 'PostToolUse'


@pytest.mark.parametrize('status', ['[]', '{}'])
def test_invalid_status_reports_protocol_json(project, status):
    runtime, spec = project
    (spec / 'bad.md').write_text(block('BAD').replace('status: active', f'status: {status}'), encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'specalign', '--root', str(runtime.root), 'hook'],
                            input=json.dumps({'hook_event_name': 'PostToolUse', 'session_id': 'bad'}),
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert 'parse_error' in json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
    assert not result.stderr


def test_unrelated_edit_does_not_repeat_reminder(project):
    runtime, spec = project
    source = spec / 'a.md'
    source.write_text(block('A'), encoding='utf-8')
    (spec / 'b.md').write_text(block('B', deps=['A']), encoding='utf-8')
    event = {'hook_event_name': 'PostToolUse', 'session_id': 'dedup'}
    assert runtime.hook(event)
    (spec / 'notes.md').write_text('Unrelated notes', encoding='utf-8')
    assert runtime.hook(event) == {}
    source.write_text(block('A', 'New relevant content'), encoding='utf-8')
    assert runtime.hook(event)


def test_explain_preserves_review_evidence_and_removed_dependency(project):
    runtime, spec = project
    source = spec / 'a.md'
    target = spec / 'b.md'
    source.write_text(block('A', 'Old requirement'), encoding='utf-8')
    target.write_text(block('B', deps=['A']), encoding='utf-8')
    initial = runtime.explain('B')
    assert initial['review'] is None
    assert set(initial['dependencies']) == {'A'}
    runtime.review('B', initial['snapshot'], 'Confirmed old requirement')
    source.write_text(block('A', 'New requirement'), encoding='utf-8')
    evidence = runtime.explain('B')
    assert not evidence['review']['matches_current_basis']
    assert evidence['review']['reason'] == 'Confirmed old requirement'
    change = next(c for c in evidence['changes'] if c['item'] == 'A')
    assert change['before']['body'] == 'Old requirement'
    assert change['after']['body'] == 'New requirement'
    assert 'Old requirement' in change['diff'] and 'New requirement' in change['diff']
    assert ('needs_review', 'B') in codes(runtime.scan())  # explain is not approval
    target.write_text(block('B', 'No longer uses A'), encoding='utf-8')
    source.unlink()
    removed = next(c for c in runtime.explain('B')['changes'] if c['item'] == 'A')
    assert removed['before']['body'] == 'Old requirement'
    assert removed['after'] is None


def test_explain_uses_matching_review_after_revert(project):
    runtime, spec = project
    source = spec / 'a.md'
    source.write_text(block('A', 'Version one'), encoding='utf-8')
    (spec / 'b.md').write_text(block('B', deps=['A']), encoding='utf-8')
    runtime.review('B', runtime.scan()['snapshot'], 'First review')
    source.write_text(block('A', 'Version two'), encoding='utf-8')
    runtime.review('B', runtime.scan()['snapshot'], 'Second review')
    source.write_text(block('A', 'Version one'), encoding='utf-8')
    result = runtime.explain('B')
    assert result['review']['matches_current_basis']
    assert result['review']['reason'] == 'First review'
    assert not result['changes']


def test_explain_cli_exposes_project_error_without_approving(project):
    runtime, spec = project
    (spec / 'a.md').write_text(block('A'), encoding='utf-8')
    (spec / 'other.md').write_text(block('OTHER', deps=['MISSING']), encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'specalign', '--root', str(runtime.root), 'explain', 'A'],
                            capture_output=True, text=True)
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report['project_error_count'] == 1
    assert report['findings'] == []
    assert report['review'] is None

