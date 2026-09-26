import json
import shutil
from pathlib import Path

import pytest

from specalign.config import load_config
from specalign.core import ProtocolError, Runtime
from specalign.storage import restore
from test_runtime import block, codes, project


def test_content_cache_and_issue_recurrence(project):
    runtime, spec = project
    file = spec / 'b.md'
    file.write_text(block('B', deps=['A']), encoding='utf-8')
    first = runtime.scan()
    assert first['stats']['parsed'] == 1
    assert runtime.scan()['stats']['cached'] == 1
    missing_id = next(f['id'] for f in first['findings'] if f['code'] == 'missing_target')
    (spec / 'a.md').write_text(block('A'), encoding='utf-8')
    runtime.scan()
    assert next(i for i in runtime.history()['issues'] if i['id'] == missing_id)['status'] == 'resolved'
    (spec / 'a.md').unlink()
    issue = next(i for i in runtime.history()['issues'] if i['id'] == missing_id)
    assert issue['occurrences'] == 2
    assert [e['status'] for e in issue['events']] == ['open', 'resolved', 'open']


def test_backup_restore_preserves_review(project, tmp_path):
    runtime, spec = project
    (spec / 'a.md').write_text(block('A') + '\n' + block('B', deps=['A']), encoding='utf-8')
    runtime.review('B', runtime.scan()['snapshot'], 'Original review')
    backup = tmp_path / 'audit.sqlite3'
    runtime.backup(backup)
    destination = tmp_path / 'restored'
    shutil.copytree(spec, destination / 'spec')
    restore(destination, backup)
    restored = Runtime(destination)
    try:
        assert not restored.scan()['findings']
        assert restored.explain('B')['review']['reason'] == 'Original review'
        with pytest.raises(ProtocolError):
            restore(destination, backup)
    finally:
        restored.close()


def test_configuration_roots_and_exclusion(project):
    runtime, spec = project
    (spec / 'skip.md').write_text(block('BAD', deps=['MISSING']), encoding='utf-8')
    (runtime.root / 'specalign.yaml').write_text('version: 1\nroots: [spec]\nexclude: ["spec/skip.md"]\n', encoding='utf-8')
    assert not runtime.scan()['findings']
    (runtime.root / 'specalign.yaml').write_text('roots: [../outside]\n', encoding='utf-8')
    with pytest.raises(ProtocolError):
        runtime.scan()


def test_configuration_resolves_project_root_before_boundary_check(project, monkeypatch):
    runtime, _ = project
    monkeypatch.chdir(runtime.root.parent)
    relative_root = Path(runtime.root.name)
    assert load_config(relative_root)['roots'] == ['spec']


def test_proposal_acceptance_and_retirement(project):
    runtime, spec = project
    (spec / 'old.md').write_text(block('OLD'), encoding='utf-8')
    proposal = block('NEW').replace('status: active', 'status: proposed\nsupersedes: [OLD]\nchallenges: [OLD]')
    (spec / 'new.md').write_text(proposal, encoding='utf-8')
    before = runtime.scan()
    assert before['items']['OLD']['effective_status'] == 'active'
    after = runtime.transition('NEW', 'accept', before['snapshot'], 'Better local option', 'agent')
    assert after['items']['OLD']['effective_status'] == 'superseded'
    assert after['items']['OLD']['status'] == 'active'
    assert ('open_challenge', 'NEW') not in codes(after)
    after = runtime.transition('NEW', 'retire', after['snapshot'], 'Feature removed', 'user')
    assert after['items']['OLD']['effective_status'] == 'superseded'
    assert len(runtime.history('NEW')['actions']) == 2


def test_typed_impact_context_and_export(project):
    runtime, spec = project
    (spec / 'all.md').write_text(block('A', 'a' * 1000) + '\n' + block('B', deps=['A']) + '\n' + block('C', refs=['A']), encoding='utf-8')
    graph = runtime.graph('A')
    assert [i['item'] for i in graph['impact']] == ['B']
    context = runtime.context('B', 500)
    assert set(context['items']) == {'A', 'B'}
    assert context['items']['A']['body_truncated']
    assert 'references' in runtime.graph(format='mermaid')


def test_compact_impact_pages_chains_and_explicit_full_graph(project):
    runtime, spec = project
    (spec / 'all.md').write_text(block('A', 'a' * 20000) + block('B', deps=['A']) +
                                 block('C', deps=['B']) + block('D', deps=['A']), encoding='utf-8')
    first = runtime.impact_report('A', limit=1)
    assert first['impacted_count'] == 3 and first['next_offset'] == 1
    assert first['impact'] == [{'item': 'B', 'status': 'active', 'chain': ['B', 'A'], 'direct': True}]
    assert 'nodes' not in first and 'edges' not in first and len(json.dumps(first)) < 1000
    second = runtime.impact_report('A', limit=1, offset=1)
    assert second['impact'][0]['item'] == 'D'
    assert runtime.impact_report('A', limit=1, offset=3)['impact'] == []
    assert runtime.impact_report('A', detail='full')['nodes']['A']['body'] == 'a' * 20000
    with pytest.raises(ProtocolError):
        runtime.impact_report('A', offset=-1)


def test_stop_continues_only_once_and_input_is_validated(project):
    runtime, spec = project
    (runtime.root / 'specalign.yaml').write_text('stop_on_errors: true\n', encoding='utf-8')
    (spec / 'bad.md').write_text(block('B', deps=['MISSING']), encoding='utf-8')
    event = {'hook_event_name': 'Stop', 'session_id': 'x'}
    assert runtime.hook(event)['decision'] == 'block'
    assert 'decision' not in runtime.hook({**event, 'stop_hook_active': True})
    with pytest.raises(ProtocolError):
        runtime.hook([])


def test_conflicting_accept_does_not_edit_file(project):
    runtime, spec = project
    (spec / 'old.md').write_text(block('OLD'), encoding='utf-8')
    (spec / 'one.md').write_text(block('ONE').replace('status: active', 'status: active\nsupersedes: [OLD]'), encoding='utf-8')
    file = spec / 'two.md'
    file.write_text(block('TWO').replace('status: active', 'status: proposed\nsupersedes: [OLD]'), encoding='utf-8')
    before = file.read_bytes()
    with pytest.raises(ProtocolError, match='already supersedes'):
        runtime.transition('TWO', 'accept', runtime.scan()['snapshot'], 'Candidate', 'agent')
    assert file.read_bytes() == before
    assert runtime.scan()['valid']


def test_accept_cannot_depend_on_its_own_replacement_target(project):
    runtime, spec = project
    (spec / 'old.md').write_text(block('OLD'), encoding='utf-8')
    file = spec / 'new.md'
    file.write_text(block('NEW', deps=['OLD']).replace('status: active', 'status: proposed\nsupersedes: [OLD]'), encoding='utf-8')
    raw = file.read_bytes()
    with pytest.raises(ProtocolError, match='cannot depend'):
        runtime.transition('NEW', 'accept', runtime.scan()['snapshot'], 'Candidate', 'agent')
    assert file.read_bytes() == raw


def test_same_missing_target_different_relations_have_independent_history(project):
    runtime, spec = project
    file = spec / 'a.md'
    file.write_text(block('A', deps=['B'], refs=['B']), encoding='utf-8')
    missing = [f for f in runtime.scan()['findings'] if f['code'] == 'missing_target']
    assert len({f['id'] for f in missing}) == 2
    file.write_text(block('A', deps=['B']), encoding='utf-8')
    history = runtime.history()['issues']
    assert next(i for i in history if i.get('relation') == 'references')['status'] == 'resolved'
    assert next(i for i in history if i.get('relation') == 'depends_on')['status'] == 'open'


def test_concurrent_scans_keep_one_snapshot_and_review_history(project):
    from concurrent.futures import ThreadPoolExecutor
    runtime, spec = project
    (spec / 'a.md').write_text(block('A') + '\n' + block('B', deps=['A']), encoding='utf-8')

    def scan(_):
        other = Runtime(runtime.root)
        try:
            return other.scan()['snapshot']
        finally:
            other.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        snapshots = list(pool.map(scan, range(8)))
    assert len(set(snapshots)) == 1
    runtime.review('B', snapshots[0], 'Single review after concurrent scans')
    assert len(runtime.history('B')['reviews']) == 1


def test_parse_failure_does_not_resolve_old_semantic_findings(project):
    runtime, spec = project
    file = spec / 'a.md'
    file.write_text(block('B', deps=['MISSING']), encoding='utf-8')
    before = runtime.scan()
    issue = next(f['id'] for f in before['findings'] if f['code'] == 'missing_target')
    file.write_text('<!-- spec\nid: B', encoding='utf-8')
    assert not runtime.scan()['valid']
    assert next(i for i in runtime.history()['issues'] if i['id'] == issue)['status'] == 'open'
