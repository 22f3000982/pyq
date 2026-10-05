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

def test_paper_import_preview_save_and_duplicate_protection(app,client):
    p=seed();h=login(client,True)
    export=client.get(f'/api/admin/ai-solutions/papers/{p.id}/export');assert export.status_code==200
    q=next(q for q in export.json['questions'] if q['question']['kind']=='MCQ')
    bundle={'format':'pyq-solutions-v1','paper_id':p.id,'solutions':[{'question_id':q['question_id'],'version':q['version'],'output':output()}]}
    body={'paper_id':p.id,'bundle':bundle}
    preview=client.post('/api/admin/ai-solutions/import',json=body,headers=h)
    assert preview.status_code==200,preview.json
    assert preview.json['items'][0]['status']=='CHECKS_PASSED';assert AISolution.query.count()==0
    saved=client.post('/api/admin/ai-solutions/import',json={**body,'save':True},headers=h)
    assert saved.json['saved']==1;assert AISolution.query.first().status=='CHECKS_PASSED'
    assert db.session.get(Question,q['question_id']).answers==['A']
    assert client.post('/api/admin/ai-solutions/import',json={**body,'save':True},headers=h).status_code==409
    assert app.test_client().get(f'/api/admin/ai-solutions/papers/{p.id}/export').status_code==401
    assert client.post('/api/admin/ai-solutions/import',json=body).status_code==403

@pytest.mark.parametrize('change',['paper','version','malformed','duplicate'])
def test_paper_import_rejects_bad_mapping_atomically(app,client,change):
    p=seed();h=login(client,True);q=Question.query.filter_by(paper_id=p.id,kind='MCQ').first()
    entry={'question_id':q.id,'version':version(snapshot(q)),'output':output()}
    bundle={'format':'pyq-solutions-v1','paper_id':p.id,'solutions':[entry]}
    if change=='paper':bundle['paper_id']=p.id+999
    if change=='version':entry['version']='old'
    if change=='malformed':entry['output']['option_explanations']={}
    if change=='duplicate':bundle['solutions'].append(dict(entry))
    r=client.post('/api/admin/ai-solutions/import',json={'paper_id':p.id,'bundle':bundle,'save':True},headers=h)
    assert r.status_code in (400,409);assert AISolution.query.count()==0

def test_replacement_is_opt_in_partial_and_unpublishes(app,client):
    p=seed();h=login(client,True);j=queued(client,p,h);finish(client,j,h)
    q=db.session.get(Question,j['question']['id']);s=AISolution.query.first();s.status='PUBLISHED';db.session.commit();sid=s.id
    entry={'question_id':q.id,'version':version(snapshot(q)),'output':{**output(),'explanation':'Updated explanation.'}}
    payload={'paper_id':p.id,'bundle':{'format':'pyq-solutions-v1','paper_id':p.id,'solutions':[entry]}}
    assert client.post('/api/admin/ai-solutions/import',json={**payload,'save':True},headers=h).status_code==409
    preview=client.post('/api/admin/ai-solutions/import',json={**payload,'replace_existing':True},headers=h)
    assert preview.json['items'][0]['replacing'] is True
    assert db.session.get(AISolution,sid).status=='PUBLISHED'
    r=client.post('/api/admin/ai-solutions/import',json={**payload,'replace_existing':True,'save':True},headers=h)
    assert r.status_code==200 and r.json['saved']==1
    updated=db.session.get(AISolution,sid);assert updated.text.startswith('Updated explanation.')
    assert updated.status=='CHECKS_PASSED' and AISolution.query.count()==1 and q.answers==['A']

def test_solution_summary_counts_current_uploads_and_published_separately(app,client):
    from backend.models import Paper
    p=seed();h=login(client,True)
    questions=Question.query.filter_by(paper_id=p.id).order_by(Question.id).all()
    for q in questions:db.session.add(AISolution(question_id=q.id,version=version(snapshot(q)),text='Solution',status='CHECKS_PASSED'))
    db.session.commit();path='/api/admin/ai-solutions/summary'
    stats=client.get(path).json['statistics']
    assert stats['papers_total']==stats['papers_complete']==1
    assert stats['papers_pending']==stats['papers_published']==0
    assert stats['questions_review']==5
    for s in AISolution.query.all():s.status='PUBLISHED'
    db.session.commit()
    assert client.get(path).json['statistics']['papers_published']==1
    questions[0].text+=' changed';db.session.commit()
    stats=client.get(path).json['statistics']
    assert stats['papers_complete']==stats['papers_published']==0
    assert stats['papers_pending']==stats['questions_pending']==stats['questions_outdated']==1
    questions[0].status='HIDDEN';db.session.commit()
    stats=client.get(path).json['statistics']
    assert stats['questions_total']==stats['questions_published']==4
    assert stats['papers_published']==1
    empty=Paper(identity='no-extracted-questions',name='Catalog only',course_id=p.course_id,term_id=p.term_id,exam_type_id=p.exam_type_id)
    archived=Paper(identity='archived',name='Archived',status='ARCHIVED',course_id=p.course_id,term_id=p.term_id,exam_type_id=p.exam_type_id)
    db.session.add_all([empty,archived]);db.session.flush()
    db.session.add(Question(paper_id=archived.id,number='1',kind='NAT',text='Hidden paper',status='AVAILABLE'));db.session.commit()
    assert client.get(path).json['statistics']['papers_total']==1
    assert client.get(path+'?course_id='+str(p.course_id)).json['papers'][0]['id']==p.id
    assert client.get(path+'?exam_type_id=999999').json['statistics']['papers_total']==0
    assert client.get(path+'?course_id=bad').status_code==400
    assert app.test_client().get(path).status_code==401

def test_import_saves_and_publishes_checked_solutions_atomically(app,client):
    p=seed();h=login(client,True)
    qs=Question.query.filter_by(paper_id=p.id).order_by(Question.id).all()
    entries=[]
    for q in qs:
        answer=q.answers if q.kind in ('MCQ','MSQ','TRUE_FALSE') else '2.5' if q.kind=='NAT' else 'Needs human assessment'
        data={'final_answer':answer,'explanation':'Reasoned answer.','option_explanations':{o.key:'Explanation of choice.' for o in q.options},'needs_review':q.kind=='SUBJECTIVE'}
        entries.append({'question_id':q.id,'version':version(snapshot(q)),'output':data})
    payload={'paper_id':p.id,'bundle':{'format':'pyq-solutions-v1','paper_id':p.id,'solutions':entries},'save':True,'publish':True}
    bad={**payload,'bundle':{**payload['bundle'],'solutions':[entries[0],{**entries[1],'version':'stale'}]}}
    assert client.post('/api/admin/ai-solutions/import',json=bad,headers=h).status_code==409
    assert AISolution.query.count()==0
    r=client.post('/api/admin/ai-solutions/import',json=payload,headers=h)
    assert r.status_code==200,r.json
    assert (r.json['saved'],r.json['published'],r.json['needs_review'])==(5,4,1)
    stats=client.get('/api/admin/ai-solutions/summary').json['statistics']
    assert stats['papers_complete']==1 and stats['papers_published']==0
    assert stats['questions_published']==4 and stats['questions_review']==1
    assert AISolution.query.filter_by(status='NEEDS_REVIEW').count()==1
    # A replacement with a discrepancy must not leave the previous published answer visible.
    change={**entries[0],'output':{**entries[0]['output'],'needs_review':True}}
    r=client.post('/api/admin/ai-solutions/import',json={**payload,'replace_existing':True,'bundle':{**payload['bundle'],'solutions':[change]}},headers=h)
    assert r.json['published']==0 and r.json['needs_review']==1
    assert AISolution.query.filter_by(question_id=qs[0].id).one().status=='NEEDS_REVIEW'
    assert client.post('/api/admin/ai-solutions/import',json={**payload,'save':False},headers=h).status_code==400
