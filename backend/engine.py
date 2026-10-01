"""Scoring and snapshots are server-owned; never accept client marks or keys."""
import math,time,re,threading
from pathlib import Path
from .models import db,Attempt,AttemptAnswer,PaperProgress
CHOICE_TYPES={'MCQ','MSQ','TRUE_FALSE'}
AUTO_TYPES=CHOICE_TYPES|{'NAT','SHORT_TEXT'}

def question_snapshot(q):
    evidence=q.evidence or {}
    text=q.text
    passage=evidence.get('shared_passage_text')
    subquestion=evidence.get('subquestion_text')
    if passage and subquestion:text=subquestion
    return {'id':q.id,'paper_id':q.paper_id,'number':q.number,'kind':q.kind,'text':text,'passage':passage,'shared_passage':bool(passage or evidence.get('shared_passage')),'options':[{'key':o.key,'text':o.text} for o in q.options], 'answers':q.answers,'answer_status':q.answer_status,'explanation':q.explanation,'marks':q.marks,'negative_marks':q.negative_marks,'tolerance':q.tolerance or 0,'topic':q.topic,'difficulty':q.difficulty,'source_page':q.source_page,'images':[{'id':i.id,'_asset_path':i.path,'alt':i.alt,'option_key':i.option_key,'token':Path(i.path).stem,**evidence.get('layout_assets',{}).get(Path(i.path).stem,{})} for i in q.images], 'source_pages':q.source_pages}

def question_order(number):
    return tuple((0,int(part)) if part.isdigit() else (1,part.lower()) for part in re.split(r'(\d+)',str(number)))

def public_question(s):
    result={k:v for k,v in s.items() if k not in ('answers','answer_status','explanation','tolerance')}
    result['images']=[{k:v for k,v in i.items() if not k.startswith('_')} for i in s.get('images',[])]
    return result

def validate_question(s,grading=False):
    if s['kind'] not in AUTO_TYPES|{'SUBJECTIVE','CODE','IMAGE'}:raise ValueError('Unsupported question type')
    if not s.get('text','').strip():raise ValueError('Question text is required')
    options=s.get('options',[]);keys=[o['key'] for o in options]
    if s['kind'] in CHOICE_TYPES and (len(keys)<2 or len(set(keys))!=len(keys)):raise ValueError('At least two unique options are required')
    for key in ('marks','negative_marks','tolerance'):
        v=s.get(key)
        if v is not None and (not isinstance(v,(int,float)) or not math.isfinite(v) or v<0):raise ValueError(f'{key} must be finite and non-negative')
    if grading and (s.get('marks') is None or s.get('negative_marks') is None):raise ValueError('Verified marks and negative marks are required for exams')
    if s.get('answer_status')=='ANSWER_AVAILABLE':
        a=s.get('answers')
        if s['kind'] in CHOICE_TYPES:
            if not isinstance(a,list) or not a or not set(a)<=set(keys):raise ValueError('Answer key must use option keys')
            if s['kind']!='MSQ' and len(a)!=1:raise ValueError('Single-answer question requires one correct key')
        if s['kind']=='NAT' and not isinstance(a,dict):
            try:
                if not math.isfinite(float(a)):raise ValueError()
            except (TypeError,ValueError):raise ValueError('NAT key must be a finite number')
    if grading and s['kind'] in AUTO_TYPES and s.get('answer_status')!='ANSWER_AVAILABLE':raise ValueError('Verified answer key required for this exam question')

def normalize_answer(s,a):
    if a in (None,'',[]):return None
    kind=s['kind']
    if kind in CHOICE_TYPES:
        if not isinstance(a,list) or any(not isinstance(v,str) for v in a):raise ValueError('Answer must be option keys')
        if len(a)!=len(set(a)) or not set(a)<={o['key'] for o in s['options']}:raise ValueError('Invalid option')
        if kind!='MSQ' and len(a)!=1:raise ValueError('Select exactly one option')
        return sorted(a)
    if kind=='NAT':
        from .numeric import number
        try:number(a)
        except Exception:raise ValueError('Enter a finite number or fraction')
        return str(a)
    if not isinstance(a,str) or len(a)>20000:raise ValueError('Answer must be text (up to 20,000 characters)')
    return a

def grade(s,a):
    if a in (None,'',[]):return {'outcome':'SKIPPED','awarded':0}
    if s['kind'] not in AUTO_TYPES or s.get('answer_status')!='ANSWER_AVAILABLE' or s.get('marks') is None or s.get('negative_marks') is None:
        return {'outcome':'UNGRADED','awarded':None}
    from .numeric import numeric_correct
    if s['kind']=='SHORT_TEXT':
        key=s['answers'];norm=(lambda v:str(v).strip()) if key.get('case_sensitive',True) else (lambda v:str(v).strip().casefold())
        correct=norm(a) in [norm(v) for v in key['values']]
    else:correct=numeric_correct(a,s['answers'],s.get('tolerance',0)) if s['kind']=='NAT' else set(a)==set(s['answers'])
    return {'outcome':'CORRECT' if correct else 'INCORRECT','awarded':s['marks'] if correct else -s['negative_marks']}

def aggregate(a):
    items=a.items;counts={key:sum(i.outcome==key for i in items) for key in ('CORRECT','INCORRECT','SKIPPED','UNGRADED')}
    score=sum(i.awarded or 0 for i in items);total=sum(i.snapshot.get('marks') or 0 for i in items)
    known_total=all(i.snapshot.get('marks') is not None for i in items)
    graded=counts['CORRECT']+counts['INCORRECT']
    return {'score':round(score,6),'total_marks':total if known_total else None,'percentage':round(score/total*100,2) if total and known_total and not counts['UNGRADED'] else None,'accuracy':round(counts['CORRECT']/graded*100,2) if graded else None,'correct':counts['CORRECT'],'incorrect':counts['INCORRECT'],'skipped':counts['SKIPPED'],'ungraded':counts['UNGRADED'],'attempted':len(items)-counts['SKIPPED'],'negative_marks':sum(-i.awarded for i in items if i.awarded is not None and i.awarded<0),'time_taken':round(max(0,a.submitted_at-a.started_at)),'pending_manual':counts['UNGRADED']>0}

RESULT_TTL_SECONDS = 3600
ACTIVE_TTL_SECONDS = 86400

def save_progress(a):
    if a.user_id is None or not a.paper_id or not a.records_progress:return
    # Database-level UPSERT handles racing submissions without duplicate rows.
    dialect=db.session.get_bind().dialect.name
    if dialect=='postgresql':
        from sqlalchemy.dialects.postgresql import insert
    elif dialect=='sqlite':
        from sqlalchemy.dialects.sqlite import insert
    else:raise ValueError('Progress requires PostgreSQL or SQLite')
    stmt=insert(PaperProgress).values(user_id=a.user_id,paper_id=a.paper_id,attempted=True,last_score=a.result['percentage'],last_attempted_at=a.submitted_at)
    stmt=stmt.on_conflict_do_update(index_elements=['user_id','paper_id'],set_={'attempted':True,'last_score':stmt.excluded.last_score,'last_attempted_at':stmt.excluded.last_attempted_at},where=stmt.excluded.last_attempted_at>=PaperProgress.last_attempted_at)
    db.session.execute(stmt)
    db.session.expire_all()

def cleanup_sessions(now=None,user_id=None,guest_hash=None):
    """Called by the worker and authenticated session endpoints; never retain history."""
    now=time.time() if now is None else now
    query=db.session.query(Attempt.id)
    if user_id is not None:query=query.filter(Attempt.user_id==user_id)
    if guest_hash is not None:query=query.filter(Attempt.guest_hash==guest_hash)
    # Expired timed sessions need no grading once their review lifetime has ended.
    ids=[id for id, in query.filter(Attempt.expires_at<=now).limit(100)]
    if ids:
        db.session.query(AttemptAnswer).filter(AttemptAnswer.attempt_id.in_(ids)).delete(synchronize_session=False)
        db.session.query(Attempt).filter(Attempt.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
    return len(ids)

_cleanup_lock=threading.Lock()
_next_cleanup=0

def maintain_temporary_sessions():
    """Bounded opportunistic cleanup also works on hosting without a worker."""
    global _next_cleanup
    if time.monotonic()<_next_cleanup or not _cleanup_lock.acquire(blocking=False):return
    try:
        cleanup_sessions()
        _next_cleanup=time.monotonic()+300
    finally:_cleanup_lock.release()

def submit_attempt(a,now=None,record_progress=True):
    if a.status!='ACTIVE':return a
    now=now or time.time();a.submitted_at=min(now,a.deadline) if a.deadline else now
    for item in a.items:
        result=grade(item.snapshot,item.answer);item.outcome=result['outcome'];item.awarded=result['awarded']
    a.status='SUBMITTED';a.result=aggregate(a)
    # Timed-out exams expire relative to their deadline, including worker downtime.
    a.expires_at=a.submitted_at+RESULT_TTL_SECONDS
    db.session.flush()
    if record_progress:save_progress(a)
    db.session.commit();return a

def expire_attempt(a):
    if a.status=='ACTIVE' and a.deadline and time.time()>=a.deadline:submit_attempt(a)

def expire_all(user_id=None,guest_hash=None):
    query=Attempt.query.filter(Attempt.status=='ACTIVE',Attempt.deadline<=time.time())
    if user_id is not None:query=query.filter(Attempt.user_id==user_id)
    if guest_hash is not None:query=query.filter(Attempt.guest_hash==guest_hash)
    for a in query.all():submit_attempt(a)
    cleanup_sessions(user_id=user_id,guest_hash=guest_hash)

def palette_state(i):
    answered=i.answer not in (None,'',[])
    if i.marked:return 'ANSWERED_AND_MARKED_FOR_REVIEW' if answered else 'MARKED_FOR_REVIEW'
    if answered:return 'ANSWERED'
    return ('NOT_ANSWERED' if i.response_touched else 'VISITED') if i.visited else 'NOT_VISITED'
