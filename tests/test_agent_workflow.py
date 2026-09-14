import json
import pytest
from specalign.core import ProtocolError
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

