import json
import pytest
from specalign.core import ProtocolError
from specalign.output import agent_report
from test_runtime import block, project


def test_summary_scope_never_hides_global_invalidity(project):
    r, spec = project
    (spec/'a.md').write_text(block('A', 'x'*20000).replace('status: active', 'status: active\nscope: one')+block('B', deps=['MISSING']))
    summary = r.check(scope='one', limit=1)
    assert 'items' not in summary and summary['project_error_count'] == 1
    assert summary['findings'] == [] and not summary['valid']
    assert r.check('full', 'one')['items']['A']['body'] == 'x'*20000
    assert len(json.dumps(summary)) < 1500


def test_batch_all_or_nothing_and_history(project, monkeypatch):
    r, spec = project
    path=spec/'a.md'; path.write_text(block('A')+block('B', deps=['A'])+block('C', deps=['B']))
    snapshot=r.scan()['snapshot']
    with pytest.raises(ProtocolError):
        r.review_batch(snapshot,[{'item':'B','reason':'checked B'}, {'item':'NO','reason':'checked NO'}])
    assert not r.history()['reviews']
    original=r._scan
    calls=0
    def changing():
        nonlocal calls
        calls+=1
        if calls==2: path.write_text(path.read_text().replace('Text','Changed'))
        return original()
    monkeypatch.setattr(r,'_scan',changing)
    with pytest.raises(ProtocolError):
        r.review_batch(snapshot,[{'item':'B','reason':'checked B'}])
    assert r.db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]==0
    assert r.db.execute('SELECT COUNT(*) FROM review_batches').fetchone()[0]==0
    monkeypatch.setattr(r,'_scan',original)
    snapshot=r.scan()['snapshot']
    result=r.review_batch(snapshot,[{'item':'B','reason':'B matches A'}, {'item':'C','reason':'C matches B'}])
    assert result['findings']==[] and 'items' not in result
    history=r.history()
    assert len(history['reviews'])==2
    assert {b['batch_id'] for b in history['batches']}=={result['batch_id']}


def test_changed_deleted_and_old_scope(project):
    r,spec=project
    path=spec/'a.md';path.write_text(block('A').replace('status: active','status: active\nscope: one'))
    old=r.scan()['snapshot']
    path.write_text(block('A').replace('status: active','status: active\nscope: two'))
    assert r.check(scope='one',since_snapshot=old)['changed_ids']==['A']
    path.unlink()
    assert r.check(since_snapshot=old)['deleted_ids']==['A']
    with pytest.raises(ProtocolError):r.check(since_snapshot='unknown')


def test_proposal_edit_is_visible_without_forcing_review(project):
    r, spec = project
    path = spec / 'plan.md'
    proposal = block('PLAN', 'Batch output is required', deps=['REQ']).replace('status: active', 'status: proposed')
    downstream = block('ACCEPTANCE', 'Test batch output', deps=['PLAN']).replace('status: active', 'status: proposed')
    path.write_text(block('REQ') + proposal + downstream, encoding='utf-8')
    baseline = r.scan()['snapshot']

    path.write_text(block('REQ') + proposal.replace('Batch output is required', 'Batch output is optional') + downstream,
                    encoding='utf-8')
    reminder = r.hook({'hook_event_name': 'PostToolUse', 'session_id': 'proposal-test'})
    message = reminder['hookSpecificOutput']['additionalContext']
    assert 'PLAN' in message and '1 proposed' in message and baseline in message
    assert r.hook({'hook_event_name': 'PostToolUse', 'session_id': 'proposal-test'}) == {}

    report = r.check(since_snapshot=baseline)
    assert report['findings'] == []
    assert report['changed_proposed_count'] == 1
    assert report['changed_items'][0] == {
        'item': 'PLAN', 'change': 'modified', 'status_before': 'proposed',
        'status_after': 'proposed', 'changed_fields': ['body'],
    }
    assert report['downstream_impact'][0]['item'] == 'ACCEPTANCE'
    assert report['downstream_impact'][0]['chain'] == ['ACCEPTANCE', 'PLAN']
    assert report['downstream_proposed_count'] == 1
    assert report['downstream_active_count'] == 0
    assert '1 proposed; declared downstream 0 active, 1 proposed' in agent_report(report, r.root)


def test_change_summary_separates_review_warning_from_proposal_impact(project):
    r, spec = project
    path = spec / 'plan.md'
    proposed = lambda ident, deps: block(ident, deps=deps).replace('status: active', 'status: proposed')
    original = block('REQ') + proposed('PLAN', ['REQ']) + proposed('ACCEPTANCE', ['PLAN']) + block('LIVE', deps=['REQ'])
    path.write_text(original, encoding='utf-8')
    initial = r.scan()['snapshot']
    r.review('LIVE', initial, 'Initial dependency check')

    path.write_text(original.replace('Text', 'Revised', 1), encoding='utf-8')
    report = r.check(since_snapshot=initial)
    assert report['changed_ids'] == ['REQ']
    assert report['changed_proposed_count'] == 0
    assert report['downstream_active_count'] == 1
    assert report['downstream_proposed_count'] == 2
    assert {entry['item']: entry['chain'] for entry in report['downstream_impact']} == {
        'LIVE': ['LIVE', 'REQ'], 'PLAN': ['PLAN', 'REQ'],
        'ACCEPTANCE': ['ACCEPTANCE', 'PLAN', 'REQ'],
    }
    assert {(finding['code'], finding['item']) for finding in report['findings']} == {('needs_review', 'LIVE')}


def test_changed_downstream_item_is_reported_once(project):
    r, spec = project
    path = spec / 'plan.md'
    path.write_text(block('A') + block('B', deps=['A']) + block('C', deps=['B']), encoding='utf-8')
    baseline = r.scan()['snapshot']
    path.write_text(block('A', 'Changed A') + block('B', 'Changed B', deps=['A']) +
                    block('C', deps=['B']), encoding='utf-8')
    report = r.check(since_snapshot=baseline)
    assert report['changed_ids'] == ['A', 'B']
    assert report['change_affected_ids'] == ['A', 'B', 'C']
    assert [entry['item'] for entry in report['downstream_impact']] == ['C']
    assert report['downstream_impact'][0]['chain'] == ['C', 'B']


@pytest.mark.parametrize('event_name', ['PostToolUse', 'Stop'])
def test_proposal_notice_survives_unrelated_structure_error(project, event_name):
    r, spec = project
    if event_name == 'Stop':
        (r.root / 'specalign.yaml').write_text('stop_on_errors: true\n', encoding='utf-8')
    path = spec / 'plan.md'
    path.write_text(block('PLAN').replace('status: active', 'status: proposed'), encoding='utf-8')
    baseline = r.scan()['snapshot']
    path.write_text(block('PLAN', 'Revised').replace('status: active', 'status: proposed') +
                    block('BROKEN', deps=['MISSING']), encoding='utf-8')
    result = r.hook({'hook_event_name': event_name, 'session_id': 'invalid-proposal'})
    message = result['reason'] if event_name == 'Stop' else result['hookSpecificOutput']['additionalContext']
    if event_name == 'Stop':
        assert result['decision'] == 'block'
    assert 'missing_target' in message and 'proposal changes' in message and baseline in message
    assert not r.check()['valid']


def test_migration_candidate_cycle_and_no_writes(project):
    r,spec=project
    path=spec/'a.md'
    path.write_text(block('OLD')+block('B',deps=['OLD'])+block('NEW',deps=['B']).replace('id: NEW','id: NEW\nsupersedes: [OLD]'))
    before=path.read_bytes()
    plan=r.migration_plan()
    assert plan['migrations']==[dict(item='B',dependency='OLD',successor_chain=['OLD','NEW'],candidate='NEW',would_create_cycle=True,requires_judgment=True)]
    assert not plan['applied'] and path.read_bytes()==before


def test_related_context_bounded_and_multiple_targets(project):
    r,spec=project
    (spec/'a.md').write_text(block('A','x'*2000)+block('B',deps=['A'])+block('C').replace('id: C','id: C\nchallenges: [A]'))
    result=r.context_many(['A','B'],500,True,2)
    assert list(result['items'])==['A','B'] and result['omitted_items']==['C']
    assert sum(len(i['body']) for i in result['items'].values())==500
    assert result['items']['B']['body_truncated']
    with pytest.raises(ProtocolError):r.context_many([])
