import time,pytest
from conftest import login
from test_engine import seed
from backend.models import db,Question,AISolution,SolutionJob,SolutionBatch
from backend.ai_solutions import checked_output,snapshot,version

def output(answer=None):return {'final_answer':answer or ['A'],'explanation':'One is correct.','option_explanations':{'A':'Correct: one.','B':'Incorrect: two.'},'needs_review':False}
def queued(client,p,h):
    r=client.post('/api/admin/ai-solutions/queue',json={'paper_id':p.id,'limit':1},headers=h)
    assert r.status_code==200,r.json
    return client.post('/api/admin/ai-solutions/worker/claim',json={},headers=h).json['job']
def finish(client,j,h,data=None):return client.post(f"/api/admin/ai-solutions/worker/{j['id']}/finish",json={'token':j['token'],'output':data or output(),'model':'test-model'},headers=h)

def test_queue_publish_and_student_privacy(app,client):
    p=seed();h=login(client,True);j=queued(client,p,h);qid=j['question']['id'];assert j['question']['answers']==['A']
    assert finish(client,j,h).json['status']=='DONE'
    row=client.get('/api/admin/ai-solutions').json['items'][0];assert row['solution']['status']=='CHECKS_PASSED' and row['question']['answers']==['A']
    guest=app.test_client();g=login(guest)
    assert guest.get('/api/admin/ai-solutions').status_code==401
    a=guest.post('/api/attempts',json={'paper_id':p.id,'mode':'exam'},headers=g).json
    path=f"/api/attempts/{a['id']}/questions/{qid}/ai-solution"
    assert guest.get(path).status_code==403
    assert 'One is correct' not in str(a)
    guest.post(f"/api/attempts/{a['id']}/submit",headers=g)
    assert guest.get(path).json=={'available':False}
    assert client.post(f'/api/admin/ai-solutions/{qid}',json={'action':'publish'},headers=h).status_code==200
    assert guest.get(path).json['available'] is True
    assert app.test_client().get(path).status_code in (401,404)
    q=db.session.get(Question,qid);assert q.answers==['A'];q.text+=' edited';db.session.commit()
    assert guest.get(path).json=={'available':False}
    assert client.post(f'/api/admin/ai-solutions/{qid}',json={'action':'publish'},headers=h).status_code==409

def test_duplicate_pause_quota_lease_recovery(app,client):
    p=seed();h=login(client,True);j=queued(client,p,h)
    qid=j['question']['id'];row=SolutionJob.query.first();batch=row.batch_id
    assert client.post('/api/admin/ai-solutions/queue',json={'question_ids':[qid]},headers=h).json['queued']==0
    expired=row.lease_token;row.lease_until=time.time()-1;db.session.commit()
    recovered=client.post('/api/admin/ai-solutions/worker/claim',json={},headers=h).json['job'];assert recovered['token']!=expired
    assert finish(client,j,h).status_code==409
    r=client.post(f"/api/admin/ai-solutions/worker/{row.id}/finish",json={'token':recovered['token'],'error':'quota'},headers=h)
    assert r.json['status']=='QUEUED';assert db.session.get(SolutionBatch,batch).status=='QUOTA_PAUSED'
    assert client.post('/api/admin/ai-solutions/worker/claim',json={},headers=h).json['job'] is None
    client.post(f'/api/admin/ai-solutions/batches/{batch}',json={'action':'resume'},headers=h)
    assert client.post('/api/admin/ai-solutions/worker/claim',json={},headers=h).json['job']
    assert client.post('/api/admin/ai-solutions/queue',json={'paper_id':p.id,'limit':31},headers=h).status_code==400
    assert client.post('/api/admin/ai-solutions/queue',json={'paper_id':p.id}).status_code==403 # CSRF

def test_mismatch_requires_admin_edit_and_practice_delivery(app,client):
    p=seed();h=login(client,True);j=queued(client,p,h);qid=j['question']['id'];finish(client,j,h,output(['B']))
    s=AISolution.query.first();assert s.status=='NEEDS_REVIEW';assert db.session.get(Question,qid).answers==['A']
    assert client.post(f'/api/admin/ai-solutions/{qid}',json={'action':'publish'},headers=h).status_code==409
    assert client.post(f'/api/admin/ai-solutions/{qid}',json={'action':'edit','text':'Admin corrected explanation.'},headers=h).status_code==200
    assert client.post(f'/api/admin/ai-solutions/{qid}',json={'action':'publish'},headers=h).status_code==200
    guest=app.test_client();g=login(guest);a=guest.post('/api/attempts',json={'paper_id':p.id,'mode':'practice'},headers=g).json
    assert guest.get(f"/api/attempts/{a['id']}/questions/{qid}/ai-solution").json['text']=='Admin corrected explanation.'
    client.post(f'/api/admin/ai-solutions/{qid}',json={'action':'unpublish'},headers=h)
    assert guest.get(f"/api/attempts/{a['id']}/questions/{qid}/ai-solution").json['available'] is False

@pytest.mark.parametrize('change',[{'final_answer':[{}]},{'option_explanations':{'A':'Only one'}},{'explanation':'<script>alert(1)</script>'}])
def test_reject_malformed_outputs(app,change):
    p=seed();q=Question.query.filter_by(paper_id=p.id,kind='MCQ').first()
    with pytest.raises(ValueError):checked_output(snapshot(q),{**output(),**change})

def test_version_stable_for_inferred_passage_and_stale_job(app,client):
    s={'text':'A long passage.\n\nWhich answer?','passage':None,'images':[]}
    assert version(s)==version({**s,'text':'Which answer?','passage':'A long passage.'})
    p=seed();h=login(client,True);j=queued(client,p,h);q=db.session.get(Question,j['question']['id']);q.answers=['B'];db.session.commit()
    assert finish(client,j,h).json['status']=='OUTDATED';assert AISolution.query.count()==0

def test_network_retries_stop_after_three_and_missing_key_flag(app,client):
    p=seed();h=login(client,True);j=queued(client,p,h)
    for n in range(3):
        r=client.post(f"/api/admin/ai-solutions/worker/{j['id']}/finish",json={'token':j['token'],'error':'network'},headers=h)
        assert r.json['status']==('FAILED' if n==2 else 'QUEUED')
        if n<2:
            row=db.session.get(SolutionJob,j['id']);row.retry_at=0;db.session.commit();j=client.post('/api/admin/ai-solutions/worker/claim',json={},headers=h).json['job']
    q=Question.query.filter_by(kind='SUBJECTIVE').first();text,final,flags=checked_output(snapshot(q),{'final_answer':'Answer','explanation':'A short explanation.','option_explanations':{},'needs_review':False})
    assert 'Source answer key unavailable' in flags

def test_full_reset_clears_solutions_and_queue(app,client):
    from backend.library_campaign import reset_library
    from backend.models import User
    p=seed();h=login(client,True);j=queued(client,p,h);finish(client,j,h)
    reset_library(User.query.first().id,cleanup_storage=False)
    assert AISolution.query.count()==SolutionJob.query.count()==SolutionBatch.query.count()==0

def test_review_batches_published_text_and_status_filters(app,client):
    p=seed();h=login(client,True);j=queued(client,p,h);qid=j['question']['id'];finish(client,j,h)
    assert client.get('/api/admin/ai-solutions?solution_status=CHECKS_PASSED').json['total']==1
    assert client.get('/api/admin/ai-solutions?solution_status=NOT_GENERATED').json['total']==4
    client.post(f'/api/admin/ai-solutions/{qid}',json={'action':'publish'},headers=h)
    guest=app.test_client();g=login(guest);a=guest.post('/api/attempts',json={'paper_id':p.id,'mode':'exam'},headers=g).json
    assert guest.get(f"/api/attempts/{a['id']}/review").status_code==409
    guest.post(f"/api/attempts/{a['id']}/submit",headers=g)
    rows=guest.get(f"/api/attempts/{a['id']}/review").json['items'];assert rows[0]['ai_solution']['available'] and not rows[1]['ai_solution']['available']
    assert client.get('/api/admin/ai-solutions?page=invalid').status_code==400

def test_full_paper_queues_over_thirty_only_missing_and_no_other_paper(app,client):
    p=seed()
    from backend.models import Paper
    other=Paper(identity='other',course_id=p.course_id,term_id=p.term_id,exam_type_id=p.exam_type_id,name='Other paper',status='AVAILABLE');db.session.add(other);db.session.flush()
    db.session.add(Question(paper_id=other.id,number='1',kind='NAT',text='Other',status='AVAILABLE'))
    for n in range(6,41):db.session.add(Question(paper_id=p.id,number=str(n),kind='NAT',text='Question '+str(n),status='AVAILABLE',answers=1,answer_status='ANSWER_AVAILABLE'))
    db.session.commit();h=login(client,True);j=queued(client,p,h);finish(client,j,h)
    r=client.post('/api/admin/ai-solutions/queue',json={'paper_id':p.id,'full_paper':True,'kind':'MCQ'},headers=h)
    assert r.status_code==200 and r.json['queued']==39
    assert SolutionJob.query.count()==40
    assert client.post('/api/admin/ai-solutions/queue',json={'paper_id':p.id,'full_paper':True},headers=h).json['queued']==0
    assert AISolution.query.first().text.startswith('One is correct')
    assert client.get('/api/admin/ai-solutions').json['batches'][0]['paper_name']==p.name
    assert client.post('/api/admin/ai-solutions/queue',json={'full_paper':True},headers=h).status_code==400
    assert client.post('/api/admin/ai-solutions/queue',json={'paper_id':p.id,'full_paper':True,'regenerate':True},headers=h).status_code==400
