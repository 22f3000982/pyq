"""Real-data API acceptance checks; no question or answer fabrication."""
import sys,json,secrets,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import create_app
from backend.models import *
from backend.ingestion import work_once
app=create_app({'RATELIMIT_ENABLED':False});client=app.test_client();report=[]
def answer(q):
    if q.kind in ('MCQ','MSQ','TRUE_FALSE'):return q.answers
    if q.kind=='SHORT_TEXT':return q.answers['values'][0]
    key=q.answers
    while key.get('kind')=='alternatives':key=key['keys'][0]
    return key['lower'] if key['kind']=='range' else key['values'][0]
with app.app_context():
    token=client.get('/api/session').json['csrf']
    reg=client.post('/api/auth/register',json={'name':'Five-paper API acceptance test','email':'five-'+secrets.token_hex(6)+'@example.test','password':secrets.token_urlsafe(24)},headers={'X-CSRF-Token':token});assert reg.status_code==201
    h={'X-CSRF-Token':reg.json['csrf']}
    for pid in json.loads(Path('demo-papers.json').read_text())['paper_ids']:
        p=db.session.get(Paper,pid);qs=Question.query.filter_by(paper_id=pid,status='AVAILABLE').all()
        assert qs and all(q.answers is not None and q.marks is not None for q in qs)
        landing=client.get(f'/api/papers/{pid}');assert landing.status_code==200 and landing.json['question_count']==len(qs)
        expected=sum(q.marks for q in qs)
        assert expected==p.source_metadata['declared_total_marks']
        for mode in ('practice','exam'):
            r=client.post('/api/attempts',json={'paper_id':pid,'mode':mode,'duration_seconds':1800},headers=h);assert r.status_code==201,r.json
            a=r.json;aid=a['id'];assert len(a['palette'])==len(qs)
            if mode=='exam':assert 1790<a['deadline']-a['server_time']<=1800
            assert client.get(f'/api/attempts/{aid}/review').status_code==409
            for q in qs:
                r=client.get(f'/api/attempts/{aid}/questions/{q.id}');assert r.status_code==200,r.json
                assert 'answers' not in r.json['question'] and 'evidence' not in r.json['question']
                for image in r.json['question']['images']:assert client.get('/api/images/'+str(image['id'])).status_code==200
                saved=client.post(f'/api/attempts/{aid}/answers',json={'question_id':q.id,'answer':answer(q),'marked':True},headers=h);assert saved.status_code==200,saved.json
                assert saved.json['state']=='ANSWERED_AND_MARKED_FOR_REVIEW'
                if mode=='practice':assert saved.json['feedback']['outcome']=='CORRECT',saved.json
                else:assert 'feedback' not in saved.json
            # Clear and restore; navigate backwards to confirm saved state.
            q=qs[0]
            cleared=client.post(f'/api/attempts/{aid}/answers',json={'question_id':q.id,'answer':None,'marked':False},headers=h);assert cleared.status_code==200
            assert client.get(f'/api/attempts/{aid}/questions/{q.id}').json['answer'] is None
            client.post(f'/api/attempts/{aid}/answers',json={'question_id':q.id,'answer':answer(q)},headers=h)
            result=client.post(f'/api/attempts/{aid}/submit',headers=h);assert result.status_code==200,result.json
            assert result.json['result']['score']==expected and result.json['result']['correct']==len(qs),result.json
            assert client.post(f'/api/attempts/{aid}/submit',headers=h).json['result']==result.json['result']
            reviewed=[];page=1
            while len(reviewed)<len(qs):
                r=client.get(f'/api/attempts/{aid}/review?page={page}').json;reviewed.extend(r['items']);page+=1
            assert len(reviewed)==len(qs) and all(i['question']['answers'] is not None for i in reviewed)
        # Check automatic submission without a live browser, using the real engine.
        a=client.post('/api/attempts',json={'paper_id':pid,'mode':'exam','duration_seconds':60},headers=h).json
        row=db.session.get(Attempt,a['id']);row.deadline=time.time()-1;db.session.commit();work_once();assert db.session.get(Attempt,a['id']).status=='SUBMITTED'
        greens=sum(any(e['kind']=='green' for es in q.evidence.get('answer_indicators',{}).values() for e in es) for q in qs)
        reds=sum(any(e['kind']=='red' for es in q.evidence.get('answer_indicators',{}).values() for e in es) for q in qs)
        report.append({'paper_id':pid,'course':p.course.name,'exam_type':p.exam_type.name,'session':p.session,'term':p.term.name,'source_url':p.source_url,'extracted_questions':len(qs),'source_instruction_items':Question.query.filter_by(paper_id=pid,status='INSTRUCTION').count(),'total_marks':expected,'source_header_questions':p.source_metadata['declared_total_questions'],'questions_with_answers':sum(q.answers is not None for q in qs),'questions_with_images':sum(bool(q.images) for q in qs),'questions_with_green_indicators':greens,'questions_with_red_indicators':reds,'extraction_status':p.status,'practice':'PASS','exam':'PASS','timer_and_timeout':'PASS','palette_navigation_clear_review':'PASS','submission_server_scoring':'PASS','result_solutions_review':'PASS','full_correct_score':expected,'duration_note':'User-selected 30 minutes; source duration is zero/unspecified','checks':'Actual Flask API requests against the processed real-paper database; browser visual checks separate'})
    Path('docs/FIVE-PAPER-TEST-REPORT.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
