import time
from datetime import datetime,timezone
from sqlalchemy import event as sql_event
from backend.analytics import report
from backend.models import db,AnalyticsEvent,Attempt
from backend.engine import cleanup_sessions
from test_engine import seed
from conftest import login


def test_permanent_browser_counts_admin_exclusion_and_modes(app,client):
    p=seed();h=login(client)
    a=client.post('/api/attempts',headers={**h,'User-Agent':'Android Mobile'},json={'paper_id':p.id,'mode':'exam'}).json
    assert AnalyticsEvent.query.count()==1
    assert client.post(f"/api/attempts/{a['id']}/switch-mode",headers=h,json={'mode':'practice'}).status_code==200
    assert client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={}).status_code==200
    assert client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={}).status_code==200
    b=client.post('/api/attempts',headers=h,json={'paper_id':p.id,'mode':'practice'}).json
    result=report('all')
    assert result['totals']['starts']==2 and result['totals']['active_browsers']==1
    assert result['totals']['completions']==1 and result['totals']['exam_completions']==0
    assert result['totals']['switched_completions']==1
    for record in Attempt.query.all():record.expires_at=time.time()-1
    db.session.commit();cleanup_sessions()
    assert AnalyticsEvent.query.count()==2
    assert client.get('/api/admin/analytics').status_code==401
    ah=login(client,True)
    assert client.post('/api/attempts',headers=ah,json={'paper_id':p.id}).status_code==201
    assert AnalyticsEvent.query.count()==2
    assert client.get('/api/admin/analytics?period=30d').status_code==200
    assert client.get('/api/admin/analytics?period=custom&start=bad&end=bad').status_code==400
    export=client.get('/api/admin/analytics?period=all&format=csv')
    assert export.status_code==200 and export.mimetype=='text/csv'
    assert 'browser_key' not in export.text


def test_analytics_failure_does_not_fail_main_action(app,client):
    p=seed();h=login(client)
    def fail(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().startswith('INSERT INTO analytics_event'):raise RuntimeError('analytics unavailable')
    sql_event.listen(db.engine,'before_cursor_execute',fail)
    try:
        a=client.post('/api/attempts',headers=h,json={'paper_id':p.id}).json
        assert 'id' in a
        assert client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={}).status_code==200
        assert db.session.get(Attempt,a['id']).status=='SUBMITTED'
        assert AnalyticsEvent.query.count()==0
    finally:sql_event.remove(db.engine,'before_cursor_execute',fail)


def test_ist_ranges_no_fabricated_history_expiry_and_new_browser(app,client):
    p=seed();h=login(client)
    a=client.post('/api/attempts',headers=h,json={'paper_id':p.id}).json
    row=AnalyticsEvent.query.one()
    row.start_day='2026-10-10';row.started_at=datetime(2026,10,9,18,31,tzinfo=timezone.utc).timestamp()
    row.expires_at=row.started_at+60;db.session.commit()
    now=datetime(2026,10,9,19,tzinfo=timezone.utc).timestamp()
    r=report('today',now=now)
    assert r['totals']['starts']==1 and r['totals']['abandoned']==1
    assert r['totals']['completions']==0 and r['totals']['average_seconds'] is None
    second=app.test_client();h2=login(second)
    assert second.post('/api/attempts',headers=h2,json={'paper_id':p.id}).status_code==201
    assert report('all')['totals']['active_browsers']==1 # future IST row outside today's range
    assert len({r.browser_key for r in AnalyticsEvent.query.all()})==2


def test_disabled_collection_and_no_extra_sql_on_question(app,client):
    app.config['ANALYTICS_ENABLED']=False;p=seed();h=login(client)
    a=client.post('/api/attempts',headers=h,json={'paper_id':p.id}).json
    assert AnalyticsEvent.query.count()==0
    assert client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={}).status_code==200
    assert AnalyticsEvent.query.count()==0


def test_restart_and_mode_switch_back_do_not_inflate_exam_completions(app,client):
    p=seed();h=login(client)
    a=client.post('/api/attempts',headers=h,json={'paper_id':p.id,'mode':'exam'}).json
    for mode in ('practice','exam'):
        assert client.post(f"/api/attempts/{a['id']}/switch-mode",headers=h,json={'mode':mode,'duration_seconds':60}).status_code==200
    assert client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={}).status_code==200
    db.session.remove();db.engine.dispose() # reopen connections: no in-memory queue needed
    totals=report('all')['totals']
    assert totals['starts']==totals['completions']==totals['switched_completions']==1
    assert totals['exam_completions']==0
