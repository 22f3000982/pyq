import time
from backend.models import db,User,Attempt,AttemptAnswer,PaperProgress,Bookmark
from backend.engine import expire_all,cleanup_sessions
from test_engine import seed
from conftest import login


def visitor(client):return {'X-CSRF-Token':client.get('/api/session').json['csrf']}


def test_guest_exam_isolated_and_no_permanent_user_data(app,client):
    p=seed();h=visitor(client);users=User.query.count()
    r=client.post('/api/attempts?bootstrap=1',headers=h,json={'paper_id':p.id,'mode':'exam','duration_seconds':5400})
    assert r.status_code==201,r.json
    a=r.json;aid=a['id'];qid=a['palette'][0]['question_id']
    assert all('answers' not in i['question'] and 'feedback' not in i for i in a['items'])
    assert db.session.get(Attempt,aid).user_id is None
    assert User.query.count()==users
    other=app.test_client();oh=visitor(other)
    for url in [f'/api/attempts/{aid}',f'/api/attempts/{aid}/status',f'/api/attempts/{aid}/review',f'/api/attempts/{aid}/questions/{qid}']:
        assert other.get(url).status_code==404
    assert other.post(f'/api/attempts/{aid}/answers',headers=oh,json={'question_id':qid,'answer':['A']}).status_code==404
    assert other.post(f'/api/attempts/{aid}/submit',headers=oh,json={}).status_code==404
    assert other.post(f'/api/attempts/{aid}/switch-mode',headers=oh,json={'mode':'practice'}).status_code==404
    assert client.post(f'/api/attempts/{aid}/answers',headers=h,json={'question_id':qid,'answer':['A']}).status_code==200
    result=client.post(f'/api/attempts/{aid}/submit',headers=h,json={})
    assert result.status_code==200 and result.json['result']['score']==4
    assert client.get(f'/api/attempts/{aid}/review').status_code==200
    assert PaperProgress.query.count()==Bookmark.query.count()==0
    assert client.get('/api/progress').json['total']==0
    record=db.session.get(Attempt,aid);record.expires_at=time.time()-1;db.session.commit()
    assert cleanup_sessions(guest_hash=record.guest_hash)==1
    assert db.session.get(Attempt,aid) is None and AttemptAnswer.query.count()==0


def test_admin_only_auth_and_csrf_remain_protected(app,client):
    h=visitor(client)
    assert client.post('/api/auth/register',headers=h,json={}).status_code==410
    assert client.get('/api/admin/stats').status_code==401
    assert client.post('/api/admin/catalog/campaign/process',headers=h,json={}).status_code==401
    assert client.post('/api/attempts',json={}).status_code==403
    ah=login(client,True)
    assert client.get('/api/admin/stats',headers=ah).status_code==200
    assert client.get('/api/session').json['user']['role']=='ADMIN'
    client.post('/api/auth/logout',headers=ah,json={})
    assert client.get('/api/admin/stats').status_code==401


def test_guest_mode_switch_wrong_practice_and_browser_bookmark_ids(app,client):
    p=seed();h=visitor(client)
    a=client.post('/api/attempts?bootstrap=1',headers=h,json={'paper_id':p.id,'mode':'practice'}).json
    qid=a['palette'][2]['question_id']
    assert client.post(f"/api/attempts/{a['id']}/answers",headers=h,json={'question_id':qid,'answer':'7'}).status_code==200
    nxt=client.post(f"/api/attempts/{a['id']}/switch-mode?bootstrap=1",headers=h,json={'mode':'exam','duration_seconds':60})
    assert nxt.status_code==200,nxt.json
    n=nxt.json;assert n['id']==a['id'];assert 'items' not in n
    bundle=client.get(f"/api/attempts/{n['id']}?bootstrap=1").json;answer=next(i for i in bundle['items'] if i['question']['id']==qid)
    assert answer['answer']=='7' and 'feedback' not in answer
    client.post(f"/api/attempts/{n['id']}/submit",headers=h,json={})
    wrong=client.post('/api/attempts',headers=h,json={'collection':'mistakes','attempt_id':n['id'],'mode':'practice'})
    assert wrong.status_code==201 and wrong.json['records_progress'] is False
    bm=client.post('/api/attempts',headers=h,json={'collection':'bookmarks','question_ids':[qid],'mode':'practice'})
    assert bm.status_code==201 and len(bm.json['palette'])==1
    assert client.post(f'/api/questions/{qid}/bookmark',headers=h,json={}).status_code==410
    assert Bookmark.query.count()==PaperProgress.query.count()==0


def test_guest_timer_expiry_and_active_cap(app,client):
    p=seed();h=visitor(client)
    a=client.post('/api/attempts',headers=h,json={'paper_id':p.id,'mode':'exam','duration_seconds':60}).json
    record=db.session.get(Attempt,a['id']);record.deadline=time.time()-1;db.session.commit()
    assert client.get(f"/api/attempts/{a['id']}/status").json['status']=='SUBMITTED'
    assert PaperProgress.query.count()==0
    for _ in range(5):assert client.post('/api/attempts',headers=h,json={'paper_id':p.id,'mode':'practice'}).status_code==201
    assert client.post('/api/attempts',headers=h,json={'paper_id':p.id,'mode':'practice'}).status_code==429


def test_mode_toggle_keeps_attempt_and_never_rebuilds_images(app,client,monkeypatch):
    p=seed();h=visitor(client)
    a=client.post('/api/attempts?bootstrap=1',headers=h,json={'paper_id':p.id,'mode':'exam','duration_seconds':5400}).json
    qid=a['palette'][0]['question_id']
    client.post(f"/api/attempts/{a['id']}/answers",headers=h,json={'question_id':qid,'answer':['A']})
    monkeypatch.setattr('backend.exam_api.question_with_image_urls',lambda *a:(_ for _ in ()).throw(AssertionError('No image rebuild during switch')))
    before=Attempt.query.count()
    r=client.post(f"/api/attempts/{a['id']}/switch-mode",headers=h,json={'mode':'practice'})
    assert r.status_code==200 and r.json['id']==a['id'] and r.json['feedback']
    assert Attempt.query.count()==before and 'items' not in r.json
    r=client.post(f"/api/attempts/{a['id']}/switch-mode",headers=h,json={'mode':'exam','duration_seconds':5400})
    assert r.status_code==200 and r.json['feedback']==[] and r.json['deadline']>time.time()
