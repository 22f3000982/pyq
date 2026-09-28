from backend.models import *
from conftest import login
from test_engine import seed

def test_mode_switch_preserves_responses_and_freezes_old_score(app,client):
    p=seed();h=login(client)
    a=client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam'},headers=h).json
    qid=a['palette'][0]['question_id']
    client.post(f"/api/attempts/{a['id']}/answers",json={'question_id':qid,'answer':['B'],'marked':True},headers=h)
    r=client.post(f"/api/attempts/{a['id']}/switch-mode",json={'mode':'practice'},headers=h)
    assert r.status_code==201
    practice=r.json;assert practice['deadline'] is None
    old=client.get(f"/api/attempts/{a['id']}").json
    assert old['status']=='SUBMITTED' and old['result']['score']==-1
    question=client.get(f"/api/attempts/{practice['id']}/questions/{qid}").json
    assert question['answer']==['B'] and question['marked'] and question['feedback']['answers']==['A']
    switched=client.post(f"/api/attempts/{practice['id']}/switch-mode",json={'mode':'exam','duration_seconds':120},headers=h)
    assert switched.status_code==201
    exam=switched.json;assert 'Assisted timed continuation' in exam['title']
    assert 110<exam['deadline']-exam['server_time']<=120
    question=client.get(f"/api/attempts/{exam['id']}/questions/{qid}").json
    assert question['answer']==['B'] and 'feedback' not in question and 'answers' not in question['question']
    assert client.post(f"/api/attempts/{a['id']}/switch-mode",json={'mode':'practice'},headers=h).status_code==409

def test_wrong_answer_practice_only_uses_this_attempt(app,client):
    p=seed();h=login(client);a=client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam'},headers=h).json
    wrong=a['palette'][0]['question_id'];correct=a['palette'][1]['question_id']
    client.post(f"/api/attempts/{a['id']}/answers",json={'question_id':wrong,'answer':['B']},headers=h)
    client.post(f"/api/attempts/{a['id']}/answers",json={'question_id':correct,'answer':['A','B']},headers=h)
    assert client.post('/api/attempts',json={'collection':'mistakes','attempt_id':a['id']},headers=h).status_code==409
    client.post(f"/api/attempts/{a['id']}/submit",headers=h)
    r=client.post('/api/attempts',json={'collection':'mistakes','attempt_id':a['id'],'mode':'practice'},headers=h)
    assert r.status_code==201 and [q['question_id'] for q in r.json['palette']]==[wrong]
    assert client.get(f"/api/attempts/{r.json['id']}/questions/{wrong}").json['answer'] is None
    other=app.test_client();ah=login(other,True)
    assert other.post('/api/attempts',json={'collection':'mistakes','attempt_id':a['id']},headers=ah).status_code==404
    assert other.post(f"/api/attempts/{r.json['id']}/switch-mode",json={'mode':'exam'},headers=ah).status_code==404

def test_available_exam_filter_excludes_catalog_only(app,client):
    p=seed();empty=Paper(identity='empty',course_id=p.course_id,term_id=p.term_id,exam_type_id=p.exam_type_id,name='Not processed');db.session.add(empty);db.session.commit()
    result=client.get('/api/papers?available=true&exam=Quiz+2&course_id='+str(p.course_id)).json
    assert result['total']==1 and result['items'][0]['id']==p.id
