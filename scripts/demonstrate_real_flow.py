"""Demonstrate the real workbook-linked paper through the actual application APIs."""
import sys,json,secrets,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import create_app
from backend.models import *
app=create_app();client=app.test_client()
with app.app_context():
    paper=Paper.query.join(Course).join(Term).join(ExamType).filter(Course.code=='CS3002',Term.name=='May 2026',ExamType.name=='Quiz 1').first()
    assert paper and Question.query.filter_by(paper_id=paper.id,status='AVAILABLE').count()==20
    token=client.get('/api/session').json['csrf']
    reg=client.post('/api/auth/register',json={'name':'Automated pipeline demonstration','email':'pipeline-'+secrets.token_hex(5)+'@example.test','password':secrets.token_urlsafe(24)},headers={'X-CSRF-Token':token});assert reg.status_code==201
    headers={'X-CSRF-Token':reg.json['csrf']}
    landing=client.get(f'/api/papers/{paper.id}').json
    practice=client.post('/api/attempts',json={'paper_id':paper.id,'mode':'practice'},headers=headers);assert practice.status_code==201
    q=Question.query.filter_by(paper_id=paper.id,number='2',status='AVAILABLE').one()
    feedback=client.post(f"/api/attempts/{practice.json['id']}/answers",json={'question_id':q.id,'answer':q.answers},headers=headers).json
    assert feedback['feedback']['outcome']=='CORRECT'
    client.post(f"/api/attempts/{practice.json['id']}/submit",headers=headers)
    exam=client.post('/api/attempts',json={'paper_id':paper.id,'mode':'exam','duration_seconds':1800},headers=headers);assert exam.status_code==201
    id=exam.json['id'];visible=client.get(f'/api/attempts/{id}/questions/{q.id}').json
    assert 'feedback' not in visible and 'answers' not in visible['question']
    client.post(f'/api/attempts/{id}/answers',json={'question_id':q.id,'answer':q.answers,'marked':True},headers=headers)
    q3=Question.query.filter_by(paper_id=paper.id,number='3',status='AVAILABLE').one()
    wrong=next(o.key for o in q3.options if o.key not in q3.answers)
    client.post(f'/api/attempts/{id}/answers',json={'question_id':q3.id,'answer':[wrong]},headers=headers)
    result=client.post(f'/api/attempts/{id}/submit',headers=headers).json['result']
    assert result['score']==5 and result['correct']==1 and result['incorrect']==1 and result['skipped']==18
    review=client.get(f'/api/attempts/{id}/review').json
    assert review['total']==20
    report={'paper':{'course':paper.course.name,'exam':paper.exam_type.name,'term':paper.term.name,'source_url':paper.source_url},'landing':landing,'practice_feedback_verified':True,'exam_keys_hidden_verified':True,'timer':'30-minute user-selected timed practice because source duration is 0/unspecified','result':result,'review_count':review['total'],'api_workflow':'register → catalog paper → practice → exam → answer → mark → submit → result → review → history','automatic':True,'manual_approval_actions':0,'visual_browser_testing':'Not completed: available browser blocks localhost'}
    Path('docs/REAL-PAPER-DEMONSTRATION.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'paper_id':paper.id,'questions':landing['question_count'],'source_marks':landing['source_metadata']['declared_total_marks'],'result':result,'manual_approval_actions':0},indent=2))
