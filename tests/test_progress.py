import time
import pytest
from backend.models import db,Question,Attempt,AttemptAnswer,PaperProgress
from backend.engine import cleanup_sessions,expire_all,save_progress
from test_engine import seed
from conftest import login

def paper():
    p=seed()
    # Real scoring engine, simple ten-question fixture to verify 70 -> 90 -> 80.
    for q in Question.query.all():db.session.delete(q)
    db.session.flush()
    from backend.models import QuestionOption
    for n in range(10):
        q=Question(paper_id=p.id,number=str(n+1),kind='MCQ',text='Test question',marks=1,negative_marks=0,answers=['A'],answer_status='ANSWER_AVAILABLE',status='AVAILABLE')
        q.options=[QuestionOption(key='A',text='Correct',position=0),QuestionOption(key='B',text='Incorrect',position=1)]
        db.session.add(q)
    db.session.commit();return p

def take(client,h,p,correct,mode='exam'):
    a=client.post('/api/attempts',json={'paper_id':p.id,'mode':mode},headers=h)
    assert a.status_code==201,a.json
    for n,i in enumerate(a.json['palette']):
        r=client.post(f"/api/attempts/{a.json['id']}/answers",json={'question_id':i['question_id'],'answer':['A' if n<correct else 'B'],'score':100000},headers=h)
        assert r.status_code==200
    r=client.post(f"/api/attempts/{a.json['id']}/submit",json={'percentage':100000},headers=h)
    assert r.status_code==200,r.json
    return r.json

def test_latest_only_upsert_card_and_retake(client):
    p=paper();h=login(client)
    assert client.get('/api/papers/'+str(p.id)).json['progress'] is None
    ids=[]
    for n in (7,9,8):
        a=take(client,h,p,n);ids.append(a['id'])
        assert a['result']['percentage']==n*10
        assert PaperProgress.query.count()==1
        progress=PaperProgress.query.one();assert progress.last_score==n*10
        assert client.get('/api/papers/'+str(p.id)).json['progress']['last_score']==n*10
        assert client.get('/api/papers?available=true').json['items'][0]['progress']['last_score']==n*10
        assert client.get('/api/progress').json['total']==1
        assert client.get('/api/attempts').json['total']==0  # active sessions only
    assert len(set(ids))==3
    # A duplicate submit of an older receipt cannot overwrite the latest score.
    assert client.post(f'/api/attempts/{ids[0]}/submit',headers=h).json['result']['percentage']==70
    assert PaperProgress.query.one().last_score==80
    assert all(a.expires_at-a.submitted_at==3600 for a in Attempt.query.all())
    cleanup_sessions(time.time()+3601)
    assert Attempt.query.count()==0 and AttemptAnswer.query.count()==0
    assert PaperProgress.query.count()==1 and PaperProgress.query.one().last_score==80
    # Retake after cleanup still uses the normal paper pipeline.
    retake=take(client,h,p,9)
    assert retake['result']['percentage']==90 and retake['id']>max(ids)
    assert PaperProgress.query.count()==1

def test_progress_is_private_and_wrong_subset_does_not_replace_score(app,client):
    p=paper();h=login(client);a=take(client,h,p,7)
    other=app.test_client();login(other,True)
    assert other.get('/api/papers/'+str(p.id)).json['progress'] is None
    assert other.get('/api/progress').json['total']==0
    anon=app.test_client();assert anon.get('/api/papers/'+str(p.id)).json['progress'] is None
    assert anon.get('/api/progress').status_code==401
    wrong=client.post('/api/attempts',json={'collection':'mistakes','attempt_id':a['id'],'mode':'practice'},headers=h).json
    assert wrong['records_progress'] is False and len(wrong['palette'])==3
    client.post(f"/api/attempts/{wrong['id']}/submit",headers=h)
    assert PaperProgress.query.one().last_score==70
    assert client.get('/api/mistakes').status_code==410

def test_timeout_progress_and_temporary_review_expiry(client):
    p=paper();h=login(client)
    a=client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam'},headers=h).json
    row=db.session.get(Attempt,a['id']);row.deadline=time.time()-1;db.session.commit()
    expire_all();assert PaperProgress.query.one().last_score==0
    assert client.get(f"/api/attempts/{a['id']}/review").status_code==200
    row.expires_at=time.time()-1;db.session.commit()
    assert client.get(f"/api/attempts/{a['id']}").status_code==410
    assert AttemptAnswer.query.count()==0
    assert PaperProgress.query.one().last_score==0

def test_late_timeout_does_not_overwrite_newer_completion(client):
    p=paper();h=login(client)
    old=client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam'},headers=h).json
    newer=take(client,h,p,9)
    row=db.session.get(Attempt,old['id']);row.deadline=newer['submitted_at']-10;db.session.commit()
    expire_all();assert PaperProgress.query.one().last_score==90

def test_practice_mode_switch_and_unknown_percentage(client):
    p=paper();h=login(client)
    a=take(client,h,p,8,mode='practice');assert PaperProgress.query.one().last_score==80
    active=client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam'},headers=h).json
    switched=client.post(f"/api/attempts/{active['id']}/switch-mode",json={'mode':'practice'},headers=h)
    assert switched.status_code==201
    assert PaperProgress.query.one().last_score==80
    q=Question.query.first();q.answers=None;q.answer_status='ANSWER_UNAVAILABLE';db.session.commit()
    result=take(client,h,p,10)
    assert result['result']['percentage'] is None
    assert PaperProgress.query.one().last_score is None

def test_concurrent_upserts_keep_one_latest_row(app):
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    from backend.models import User
    p=paper();pid=p.id;uid=User.query.first().id
    def write(n):
        with app.app_context():
            save_progress(SimpleNamespace(user_id=uid,paper_id=pid,records_progress=True,result={'percentage':float(n)},submitted_at=float(n)))
            db.session.commit();db.session.remove()
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(write,[3,8,2,10,1,9,4,7,6,5]))
    db.session.expire_all()
    assert PaperProgress.query.count()==1
    assert PaperProgress.query.one().last_score==10
    assert PaperProgress.query.one().last_attempted_at==10
