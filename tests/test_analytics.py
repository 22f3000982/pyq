import time
from datetime import datetime, timezone
from backend.analytics import persist, report, Collector, snapshot
from backend.models import db, AnalyticsDaily, AnalyticsReceipt, Attempt
from backend.engine import cleanup_sessions
from test_engine import seed
from conftest import login

def test_live_start_submit_deduplicates_and_survives_cleanup(app,client):
    p=seed();h=login(client)
    started=client.post('/api/attempts',headers={**h,'User-Agent':'Mozilla Android Mobile'},json={'paper_id':p.id}).json
    writer=app.extensions['analytics']
    assert writer.queue.qsize()==1 and AnalyticsDaily.query.count()==0
    writer.flush()
    a=db.session.get(Attempt,started['id'])
    # Switching modes must not split one attempt between aggregate groups.
    a.mode='exam';db.session.commit()
    assert client.post(f"/api/attempts/{a.id}/submit",headers=h,json={}).status_code==200
    event=snapshot(a)
    writer.put(event);writer.flush()
    db.session.expire_all()
    row=AnalyticsDaily.query.one()
    assert (row.starts,row.completions,row.device,row.mode)==(1,1,'mobile','practice')
    assert row.elapsed_seconds>=0
    a.expires_at=time.time()-1;db.session.commit();cleanup_sessions()
    assert Attempt.query.count()==0 and AnalyticsDaily.query.count()==1
    assert client.get('/api/admin/analytics').status_code==401
    login(client,True)
    result=client.get('/api/admin/analytics?period=all')
    assert result.status_code==200 and result.json['totals']['completion_rate']==100
    assert result.json['papers'][0]['name']==p.name
    assert client.get('/api/admin/analytics?period=invalid').status_code==400

def event(key,started,completed=None):
    return dict(key=key,started_at=started,submitted_at=completed,automatic=False,
                paper_key='paper',paper_name='Paper',course_key='course',course_name='Course',device='desktop',mode='exam')

def test_ist_boundaries_and_completion_before_start(app):
    now=datetime(2026,10,9,19,tzinfo=timezone.utc).timestamp() # October 10 in IST
    yesterday=datetime(2026,10,9,18,29,tzinfo=timezone.utc).timestamp()
    today=yesterday+120
    complete=event('a',today,today+60)
    persist(db.engine,[complete,event('a',today),complete,event('b',yesterday)],now=now)
    result=report('today',now=now)
    assert result['totals']['starts']==result['totals']['completions']==1
    assert result['totals']['average_seconds']==60
    assert report('7d',now=now)['totals']['starts']==2
    assert AnalyticsReceipt.query.count()==2

def test_queue_overflow_and_write_failure_do_not_fail_exam(app,client,monkeypatch):
    app.config['ANALYTICS_QUEUE_SIZE']=1
    writer=app.extensions['analytics']=Collector(app)
    p=seed();h=login(client)
    a=client.post('/api/attempts',headers=h,json={'paper_id':p.id}).json
    assert client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={}).status_code==200
    assert writer.dropped==1
    monkeypatch.setattr('backend.analytics.persist',lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('offline')))
    writer.flush()
    assert writer.failed==1 and writer.queue.empty()
    assert db.session.get(Attempt,a['id']).status=='SUBMITTED'

def test_old_replay_ignored_and_receipts_pruned(app):
    now=time.time();old=now-31*86400
    db.session.add(AnalyticsReceipt(key='old',started_at=old,completed=True));db.session.commit()
    persist(db.engine,[event('old',old,old+60),event('fresh',now)],now=now)
    assert AnalyticsReceipt.query.count()==1
    assert AnalyticsDaily.query.one().starts==1

def test_timer_expiry_counted_once_and_preexisting_sessions_excluded(app,client):
    p=seed();h=login(client)
    a=client.post('/api/attempts',headers=h,json={'paper_id':p.id,'mode':'exam','duration_seconds':60}).json
    record=db.session.get(Attempt,a['id']);record.deadline=time.time()-1;db.session.commit()
    assert client.get(f"/api/attempts/{a['id']}/status").json['status']=='SUBMITTED'
    app.extensions['analytics'].flush();db.session.expire_all()
    assert AnalyticsDaily.query.one().automatic==1
    assert client.get(f"/api/attempts/{a['id']}/status").status_code==200
    assert app.extensions['analytics'].queue.empty()
    record.analytics_context=None
    assert snapshot(record) is None

def test_background_writer_does_not_block_submit(app,client,monkeypatch):
    import threading
    writing,release=threading.Event(),threading.Event()
    def slow_database(*args,**kwargs):
        writing.set()
        assert release.wait(5)
    monkeypatch.setattr('backend.analytics.persist',slow_database)
    app.config['ANALYTICS_MANUAL_FLUSH']=False
    p=seed();h=login(client);writer=app.extensions['analytics']
    try:
        a=client.post('/api/attempts',headers=h,json={'paper_id':p.id}).json
        assert writing.wait(3)
        assert client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={}).status_code==200
        assert not release.is_set()  # Main submit finished while analytics was blocked.
    finally:
        release.set();writer.close()
