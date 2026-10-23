import time
from datetime import datetime,timezone
from sqlalchemy import event as sql_event
from backend.models import db,AnalyticsEvent,AnalyticsQuestionDay,Attempt,Question,AISolution,ContentReport
from backend.analytics import report,day,question_attention
from backend.ai_solutions import version
from backend.engine import question_snapshot,cleanup_sessions
from conftest import login
from test_engine import seed

def start(client,p,h,mode='exam'):
    return client.post('/api/attempts',headers=h,json={'paper_id':p.id,'mode':mode}).json

def test_admin_scores_question_totals_and_double_submit_survive_cleanup(app,client):
    p=seed();q=Question.query.filter_by(paper_id=p.id,number='1').one();h=login(client,True)
    a=start(client,p,h)
    assert client.post(f"/api/attempts/{a['id']}/answers",headers=h,json={'question_id':q.id,'answer':['A']}).status_code==200
    for _ in range(2):assert client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={}).status_code==200
    event=AnalyticsEvent.query.one();assert event.score_percent==20
    assert event.exam_name=='Quiz 2'
    total=AnalyticsQuestionDay.query.filter_by(question_id=q.id).one();assert total.correct==1 and total.mode=='exam'
    assert AnalyticsQuestionDay.query.count()==5
    assert not {'answer','browser_key','guest_hash','user_id'}&set(AnalyticsQuestionDay.__table__.columns.keys())
    for attempt in Attempt.query.all():attempt.expires_at=time.time()-1
    db.session.commit();cleanup_sessions()
    assert Attempt.query.count()==0
    assert AnalyticsEvent.query.one().score_percent==20 and AnalyticsQuestionDay.query.count()==5
    r=report('all');assert r['totals']['scored_exams']==1 and r['totals']['average_score']==20

def test_assisted_and_practice_scores_are_not_exam_scores(app,client):
    p=seed();h=login(client)
    a=start(client,p,h)
    client.post(f"/api/attempts/{a['id']}/switch-mode",headers=h,json={'mode':'practice'})
    client.post(f"/api/attempts/{a['id']}/switch-mode",headers=h,json={'mode':'exam','duration_seconds':60})
    client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={})
    b=start(client,p,h,'practice');client.post(f"/api/attempts/{b['id']}/submit",headers=h,json={})
    assert all(r.score_percent is None for r in AnalyticsEvent.query.all())
    assert {r.mode for r in AnalyticsQuestionDay.query.all()}=={'practice'}
    assert report('all')['totals']['scored_exams']==0

def test_question_write_failure_keeps_main_submission(app,client):
    p=seed();h=login(client);a=start(client,p,h)
    def fail(conn,cursor,statement,parameters,context,executemany):
        if 'INSERT INTO analytics_question_day' in statement:raise RuntimeError('aggregate failed')
    sql_event.listen(db.engine,'before_cursor_execute',fail)
    try:
        r=client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={})
        assert r.status_code==200 and r.json['status']=='SUBMITTED'
        assert AnalyticsEvent.query.one().completed_at is None
        assert AnalyticsQuestionDay.query.count()==0
    finally:sql_event.remove(db.engine,'before_cursor_execute',fail)

def test_zero_filled_trend_returning_browsers_heatmap_and_filters(app,client,monkeypatch):
    now=datetime(2026,10,23,8,tzinfo=timezone.utc).timestamp()
    def add(key,browser,when,course='ONE',mode='exam'):
        return AnalyticsEvent(key=key,browser_key=browser,started_at=when,start_day=day(when),paper_key='p'+course,paper_name='Paper',course_key=course,course_name=course,initial_mode=mode,device='mobile',expires_at=when+3600,automatic=False)
    monkeypatch.setattr('backend.analytics.time.time',lambda:now)
    old=datetime(2026,10,10,8,tzinfo=timezone.utc).timestamp()
    db.session.add_all([add('old','repeat',old),add('a','repeat',now),add('b','new',now),add('c','other',now,'TWO','practice')]);db.session.commit()
    r=report('7d',now=now,course='ONE',mode='exam')
    assert len(r['trend'])==7 and sum(d['starts'] for d in r['trend'])==2
    assert sum(d['starts']==0 for d in r['trend'])==6
    assert r['totals']['returning_browsers']==1 and r['totals']['new_browsers']==1
    assert r['comparison']['totals']['starts']==1 and r['comparison']['change']['starts']==100
    assert report('7d',now=now,course='TWO')['comparison']['change']['starts'] is None
    assert r['heatmap']==[dict(weekday=4,hour=13,starts=2)]
    assert r['weekly'][0]['active_browsers']==2
    assert 'browser_key' not in str(r)
    login(client,True)
    assert client.get('/api/admin/analytics?mode=invalid').status_code==400
    response=client.get('/api/admin/analytics?course=ONE&mode=exam&period=all')
    assert response.status_code==200 and response.json['totals']['starts']==3
    assert client.get('/api/admin/analytics?course=TWO&format=csv').mimetype=='text/csv'

def test_needs_attention_counts_published_current_solutions_and_reports(app,client):
    p=seed();q=Question.query.filter_by(paper_id=p.id,number='1').one();h=login(client)
    start(client,p,h)
    db.session.add(AISolution(question_id=q.id,version=version(question_snapshot(q)),text='Explanation',status='PUBLISHED'))
    db.session.add(ContentReport(question_id=q.id,guest_hash='test',issue='TEXT',status='OPEN'))
    db.session.commit()
    r=report('all');attention=r['attention']
    assert attention['coverage']==dict(questions=5,published=1,percent=20)
    assert attention['open_reports']==1 and attention['reports'][0]['question_id']==q.id
    assert attention['unsolved'][0]['missing']==4
    assert attention['unsolved'][0]['id']==p.id

def test_question_accuracy_requires_enough_samples_and_current_version(app,client):
    p=seed();q=Question.query.filter_by(paper_id=p.id,number='1').one();v=version(question_snapshot(q));today=day(time.time())
    stat=AnalyticsQuestionDay(day=today,paper_key=p.identity,question_id=q.id,version=v,mode='exam',number='1',correct=1,incorrect=18,partial=0,skipped=0,ungraded=0)
    db.session.add(stat);db.session.commit()
    assert question_attention(None,today,None,None)==[]
    stat.incorrect=19;db.session.commit()
    rows=question_attention(None,today,None,None);assert len(rows)==1 and rows[0]['graded']==20 and rows[0]['accuracy']==5
    assert question_attention(None,today,None,'practice')==[]
    q.text+=' edited';db.session.commit()
    assert question_attention(None,today,None,None)==[]

def test_question_navigation_does_not_write_analytics(app,client):
    p=seed();h=login(client);a=start(client,p,h);qid=a['palette'][0]['question_id'];writes=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if 'analytics_' in statement.lower() and statement.lstrip().lower().startswith(('insert','update','delete')):writes.append(statement)
    sql_event.listen(db.engine,'before_cursor_execute',capture)
    try:assert client.get(f"/api/attempts/{a['id']}/questions/{qid}").status_code==200
    finally:sql_event.remove(db.engine,'before_cursor_execute',capture)
    assert writes==[]

def test_submit_uses_one_bulk_question_write_not_one_per_question(app,client):
    p=seed();h=login(client);a=start(client,p,h);writes=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().startswith('INSERT INTO analytics_question_day'):writes.append(statement)
    sql_event.listen(db.engine,'before_cursor_execute',capture)
    try:assert client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={}).status_code==200
    finally:sql_event.remove(db.engine,'before_cursor_execute',capture)
    assert len(writes)==1 and AnalyticsQuestionDay.query.count()==5
