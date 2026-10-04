import pytest
from backend.engine import grade
from backend.models import db,Question
from test_engine import seed
from test_guest_access import visitor

@pytest.mark.parametrize('answer,outcome,marks', [(['A','B','C'],'CORRECT',4),(['A','B'],'PARTIAL',8/3),(['C'],'PARTIAL',4/3),(['A','D'],'INCORRECT',0),(['D'],'INCORRECT',0),([], 'SKIPPED',0)])
def test_proportional_msq(answer,outcome,marks):
    s={'kind':'MSQ','answers':['A','B','C'],'answer_status':'ANSWER_AVAILABLE','marks':4,'negative_marks':7,'msq_scoring':'proportional-v1'}
    r=grade(s,answer);assert r['outcome']==outcome;assert r['awarded']==pytest.approx(marks)

def test_partial_feedback_and_submit_agree(client):
    p=seed();h=visitor(client)
    q=Question.query.filter_by(kind='MSQ').first();qid=q.id
    a=client.post('/api/attempts?bootstrap=1',headers=h,json={'paper_id':p.id,'mode':'practice'}).json
    row=client.post(f"/api/attempts/{a['id']}/answers",headers=h,json={'question_id':qid,'answer':['A']}).json
    assert row['feedback']['outcome']=='PARTIAL' and row['feedback']['awarded']==2
    done=client.post(f"/api/attempts/{a['id']}/submit",headers=h,json={}).json
    assert done['result']['score']==2 and done['result']['partial']==1 and done['result']['attempted']==1
    assert done['result']['negative_marks']==0
    review=client.get(f"/api/attempts/{a['id']}/review").json
    assert next(i for i in review['items'] if i['question']['id']==qid)['awarded']==2

def test_legacy_snapshots_keep_exact_match_scoring():
    s={'kind':'MSQ','answers':['A','B'],'answer_status':'ANSWER_AVAILABLE','marks':4,'negative_marks':0}
    assert grade(s,['A'])=={'outcome':'INCORRECT','awarded':0}
