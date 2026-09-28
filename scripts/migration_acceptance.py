"""Exercise migrated real papers through Flask APIs, rolling all test writes back."""
import json,secrets,time
from pathlib import Path
from backend.models import db,Paper,Question,Attempt,PaperProgress
from backend.engine import expire_all
ROOT=Path(__file__).resolve().parents[1]


def source_answer(q):
    if q.kind in ('MCQ','MSQ','TRUE_FALSE'):return q.answers
    if q.kind=='SHORT_TEXT':return q.answers['values'][0]
    key=q.answers
    while isinstance(key,dict) and key.get('kind')=='alternatives':key=key['keys'][0]
    if not isinstance(key,dict):return str(key)
    return key['lower'] if key['kind']=='range' else key['values'][0]


def five_paper_acceptance(app):
    reports=[]
    with app.app_context():
        db.session.remove();engine=db.engine;conn=engine.connect();outer=conn.begin()
        if engine.dialect.name=='sqlite':conn.exec_driver_sql('BEGIN')
        # Every API commit only releases its savepoint, never the outer transaction.
        # The imported public data is restored by outer.rollback() below.
        db.engines[None]=conn;db.session.configure(join_transaction_mode='create_savepoint')
        try:
            client=app.test_client();csrf=client.get('/api/session').json['csrf']
            registration=client.post('/api/auth/register',json={'email':'migration-check-'+secrets.token_hex(8)+'@example.test','name':'Migration verification','password':secrets.token_urlsafe(24)},headers={'X-CSRF-Token':csrf})
            if registration.status_code!=201:raise RuntimeError('Verification account creation failed')
            headers={'X-CSRF-Token':registration.json['csrf']};uid=registration.json['user']['id']
            paper_ids=json.loads((ROOT/'demo-papers.json').read_text())['paper_ids']
            for pid in paper_ids:
                p=db.session.get(Paper,pid)
                if p is None:raise RuntimeError('Required real demo paper missing: '+str(pid))
                questions=Question.query.filter_by(paper_id=p.canonical_paper_id or pid,status='AVAILABLE').all()
                if not questions or not all(q.answers is not None and q.marks is not None for q in questions):raise RuntimeError('Missing reliable source keys/marks for demo paper '+str(pid))
                expected=sum(q.marks for q in questions)
                for mode in ('practice','exam'):
                    response=client.post('/api/attempts',json={'paper_id':pid,'mode':mode,'duration_seconds':5400},headers=headers)
                    assert response.status_code==201,response.json
                    attempt=response.json;aid=attempt['id']
                    assert len(attempt['palette'])==len(questions)
                    assert [int(i['number']) for i in attempt['palette']]==sorted(int(q.number) for q in questions)
                    assert client.get(f'/api/attempts/{aid}/review').status_code==409
                    if mode=='exam':assert 5370<attempt['deadline']-attempt['server_time']<=5400
                    for q in questions:
                        shown=client.get(f'/api/attempts/{aid}/questions/{q.id}');assert shown.status_code==200
                        assert 'answers' not in shown.json['question']
                        for image in shown.json['question']['images']:assert client.get('/api/images/'+str(image['id'])).status_code==200
                        saved=client.post(f'/api/attempts/{aid}/answers',json={'question_id':q.id,'answer':source_answer(q),'marked':True},headers=headers)
                        assert saved.status_code==200,saved.json
                        if mode=='exam':assert 'feedback' not in saved.json
                        else:assert saved.json['feedback']['outcome']=='CORRECT'
                        # NAT and other entered answers survive the actual API reload.
                        assert client.get(f'/api/attempts/{aid}/questions/{q.id}').json['answer'] is not None
                    q=questions[0]
                    assert client.post(f'/api/attempts/{aid}/answers',json={'question_id':q.id,'answer':None},headers=headers).status_code==200
                    assert client.get(f'/api/attempts/{aid}/questions/{q.id}').json['answer'] is None
                    client.post(f'/api/attempts/{aid}/answers',json={'question_id':q.id,'answer':source_answer(q)},headers=headers)
                    result=client.post(f'/api/attempts/{aid}/submit',headers=headers)
                    assert result.status_code==200 and result.json['result']['score']==expected,result.json
                    assert result.json['result']['correct']==len(questions)
                    assert client.post(f'/api/attempts/{aid}/submit',headers=headers).json['result']==result.json['result']
                    assert client.get(f'/api/attempts/{aid}/review').json['total']==len(questions)
                    assert PaperProgress.query.filter_by(user_id=uid,paper_id=pid).count()==1
                    assert client.get('/api/papers/'+str(pid)).json['progress']['last_score']==100
                # A retake with no answers must REPLACE 100%, not append history.
                again=client.post('/api/attempts',json={'paper_id':pid,'mode':'exam','duration_seconds':60},headers=headers).json
                timed=db.session.get(Attempt,again['id']);timed.deadline=time.time()-0.000001;db.session.commit();expire_all()
                assert db.session.get(Attempt,again['id']).status=='SUBMITTED'
                assert PaperProgress.query.filter_by(user_id=uid,paper_id=pid).one().last_score==0
                reports.append({'paper_id':pid,'course':p.course.name,'exam_type':p.exam_type.name,'term':p.term.name,'questions':len(questions),'total_marks':expected,'questions_with_answers':sum(q.answers is not None for q in questions),'questions_with_images':sum(bool(q.images) for q in questions),'nat_questions':sum(q.kind=='NAT' for q in questions),'extraction_status':p.status,'practice':'PASS','exam':'PASS','nat_persistence':'PASS' if any(q.kind=='NAT' for q in questions) else 'NOT_APPLICABLE','scoring':'PASS','review':'PASS','retake_latest_progress':'PASS','timer_timeout':'PASS'})
            assert PaperProgress.query.filter_by(user_id=uid).count()==5
        finally:
            db.session.remove();outer.rollback();conn.close();db.engines[None]=engine
            db.session.configure(join_transaction_mode='conditional_savepoint')
    return reports
