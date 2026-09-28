import time,pytest
from backend.models import *
from backend.engine import grade,normalize_answer,question_snapshot
from conftest import login

def seed():
    c=Course(name='DEMO DATA — Test Course',code='TEST');t=Term(name='Test 2026',year=2026,month=1);e=ExamType(name='Quiz 2')
    db.session.add_all([c,t,e]);db.session.flush()
    p=Paper(identity='demo',course_id=c.id,term_id=t.id,exam_type_id=e.id,name='DEMO DATA',duration_seconds=60,status='AVAILABLE');db.session.add(p);db.session.flush()
    for n,(kind,answers) in enumerate([('MCQ',['A']),('MSQ',['A','B']),('NAT',2.5),('TRUE_FALSE',['A']),('SUBJECTIVE',None)]):
        q=Question(paper_id=p.id,number=str(n+1),kind=kind,text='DEMO DATA — question '+str(n),answers=answers,answer_status='ANSWER_AVAILABLE' if answers is not None else 'ANSWER_UNAVAILABLE',marks=4,negative_marks=1,tolerance=.01,status='AVAILABLE',topic='Test topic')
        if kind in ('MCQ','MSQ','TRUE_FALSE'):q.options=[QuestionOption(key='A',text='One',position=0),QuestionOption(key='B',text='Two',position=1)]
        db.session.add(q)
    db.session.commit();return p

@pytest.mark.parametrize('kind,key,response,expected',[('MCQ',['A'],['A'],'CORRECT'),('MCQ',['A'],['B'],'INCORRECT'),('MSQ',['A','B'],['B','A'],'CORRECT'),('MSQ',['A','B'],['A'],'INCORRECT'),('NAT',2.5,2.505,'CORRECT'),('NAT',2.5,3,'INCORRECT'),('TRUE_FALSE',['A'],['A'],'CORRECT'),('MCQ',['A'],None,'SKIPPED'),('SUBJECTIVE',None,'text','UNGRADED')])
def test_scoring(kind,key,response,expected):
    r=grade({'kind':kind,'answers':key,'answer_status':'ANSWER_AVAILABLE','marks':4,'negative_marks':1,'tolerance':.01},response)
    assert r['outcome']==expected
    if expected=='INCORRECT':assert r['awarded']==-1

@pytest.mark.parametrize('value',['nan','inf',float('-inf'),'abc',{}])
def test_bad_numeric(value):
    with pytest.raises(ValueError):normalize_answer({'kind':'NAT'},value)

def test_exam_lifecycle(client,app):
    p=seed();h=login(client);r=client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam'},headers=h);assert r.status_code==201,r.json
    a=r.json;aid=a['id'];qid=a['palette'][0]['question_id']
    visible=client.get(f'/api/attempts/{aid}/questions/{qid}').json
    assert 'answers' not in visible['question'] and 'feedback' not in visible
    assert client.get(f'/api/attempts/{aid}/review').status_code==409
    r=client.post(f'/api/attempts/{aid}/answers',json={'question_id':qid,'answer':['A'],'marked':True,'score':999},headers=h)
    assert r.json['state']=='ANSWERED_AND_MARKED_FOR_REVIEW' and 'feedback' not in r.json
    # Later admin edits cannot change an in-flight attempt.
    db.session.get(Question,qid).answers=['B'];db.session.commit()
    r=client.post(f'/api/attempts/{aid}/submit',headers=h);assert r.json['result']['score']==4
    assert r.json['result']['skipped']==4
    assert client.post(f'/api/attempts/{aid}/submit',headers=h).json['result']==r.json['result']
    assert client.post(f'/api/attempts/{aid}/answers',headers=h,json={'question_id':qid,'answer':['B']}).status_code==409
    assert client.get('/api/attempts').json['total']==0
    assert client.get(f'/api/attempts/{aid}/review').json['items'][0]['question']['answers']==['A']

def test_expiry_ownership_collections(client,app):
    p=seed();h=login(client)
    a=client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam'},headers=h).json;aid=a['id'];qid=a['palette'][0]['question_id']
    client.post(f'/api/attempts/{aid}/answers',json={'question_id':qid,'answer':['B']},headers=h)
    attempt=db.session.get(Attempt,aid);attempt.deadline=time.time()-1;db.session.commit()
    assert client.post(f'/api/attempts/{aid}/answers',json={'question_id':qid,'answer':['A']},headers=h).status_code==409
    assert client.get(f'/api/attempts/{aid}').json['result']['score']==-1
    assert client.get('/api/mistakes').status_code==410
    for _ in range(2):assert client.post(f'/api/questions/{qid}/bookmark',headers=h).status_code==200
    assert client.get('/api/bookmarks').json['total']==1
    for kind in ('bookmarks',):
        a=client.post('/api/attempts',json={'collection':kind,'mode':'practice'},headers=h).json
        assert len(a['palette'])==1
    other=app.test_client();h2=login(other,True)
    assert other.get(f'/api/attempts/{aid}').status_code==404

def test_practice_and_missing_metadata(client,app):
    p=seed();p.duration_seconds=None;db.session.commit();h=login(client)
    assert client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam'},headers=h).status_code==409
    a=client.post('/api/attempts',json={'paper_id':p.id,'mode':'practice'},headers=h).json;q=a['palette'][0]['question_id']
    r=client.post(f"/api/attempts/{a['id']}/answers",json={'question_id':q,'answer':['A']},headers=h)
    assert r.json['feedback']['answers']==['A']
    r=client.post(f"/api/attempts/{a['id']}/answers",json={'question_id':q,'answer':None},headers=h)
    assert r.json['state']=='NOT_ANSWERED'
