"""Fresh-library reset and systematic catalog campaign helpers."""
import time
from collections import defaultdict
from sqlalchemy import func,or_
from sqlalchemy.orm import joinedload
from flask import current_app
from .models import *
from .storage import project_prefix_inventory,purge_project_prefix,StorageError
from .content_cache import invalidate

SUCCESS={'AVAILABLE','PARTIAL','DUPLICATE'}
FAILED={'PROCESSING_FAILED','EXTRACTION_FAILED'}
ACTIVE={'FETCH_QUEUED','QUEUED','FETCHING','PROCESSING'}

def library_inventory(include_storage=True):
    counts={
        'users':User.query.count(),'courses':Course.query.count(),'terms':Term.query.count(),'exam_types':ExamType.query.count(),
        'papers':Paper.query.count(),'questions':Question.query.count(),'available_questions':Question.query.filter_by(status='AVAILABLE').count(),
        'images':QuestionImage.query.count(),'options':QuestionOption.query.count(),'source_entries':SourceEntry.query.count(),
        'ingestion_files':IngestionFile.query.count(),'ingestion_batches':IngestionBatch.query.count(),'imports':ImportRun.query.count(),
        'attempts':Attempt.query.count(),'progress':PaperProgress.query.count(),'bookmarks':Bookmark.query.count(),
        'reviews':QuestionReview.query.count(),
    }
    counts['ready_papers']=db.session.query(Question.paper_id).filter(Question.status=='AVAILABLE').distinct().count()
    now=time.time();stale_before=now-1800
    active_q=IngestionFile.query.filter(IngestionFile.status.in_(['FETCHING','PROCESSING']))
    counts['active_ingestion']=active_q.count()
    counts['stale_ingestion']=active_q.filter(or_(IngestionFile.started_at.is_(None),IngestionFile.started_at<stale_before)).count()
    counts['live_ingestion']=counts['active_ingestion']-counts['stale_ingestion']
    result={'counts':counts}
    if include_storage:
        try:result['storage']=project_prefix_inventory()
        except StorageError as exc:result['storage']={'enabled':True,'error':str(exc)}
    return result

def reset_library(user_id,cleanup_storage=True,cancel_active=False):
    inventory=library_inventory(include_storage=False)
    if inventory['counts']['live_ingestion'] and not cancel_active:
        raise RuntimeError('A paper is genuinely still processing. Confirm cancellation to stop it and continue the full library reset.')
    # A full reset owns the content lifecycle. Old PROCESSING markers can survive
    # a deploy/worker restart; explicit cancellation prevents those zombie rows
    # from blocking a clean start forever.
    active=IngestionFile.query.filter(IngestionFile.status.in_(['FETCHING','PROCESSING'])).all()
    if active:
        now=time.time()
        for f in active:
            f.status='PAUSED';f.finished_at=now;f.error='Cancelled by administrator during full PYQ library reset.'
            f.events=(f.events or [])+[{'time':now,'stage':'RESET_CANCELLED','message':'Cancelled by administrator during full PYQ library reset.'}]
        db.session.commit()
    # Delete dependent content explicitly so PostgreSQL and SQLite behave the same.
    Bookmark.query.delete(synchronize_session=False)
    QuestionReview.query.delete(synchronize_session=False)
    AttemptAnswer.query.delete(synchronize_session=False)
    Attempt.query.delete(synchronize_session=False)
    PaperProgress.query.delete(synchronize_session=False)
    QuestionImage.query.delete(synchronize_session=False)
    QuestionOption.query.delete(synchronize_session=False)
    Question.query.delete(synchronize_session=False)
    SourceEntry.query.delete(synchronize_session=False)
    IngestionFile.query.delete(synchronize_session=False)
    IngestionBatch.query.delete(synchronize_session=False)
    Paper.query.update({Paper.canonical_paper_id:None},synchronize_session=False)
    Paper.query.delete(synchronize_session=False)
    ImportRun.query.delete(synchronize_session=False)
    ExamType.query.delete(synchronize_session=False)
    Term.query.delete(synchronize_session=False)
    Course.query.delete(synchronize_session=False)
    db.session.flush()
    report={'mode':'controlled_library_reset','created_at':time.time(),'requested_by':user_id,'before':inventory['counts']}
    db.session.add(ImportRun(workbook_hash=None,report=report))
    db.session.commit();invalidate()
    storage={'enabled':False,'deleted':0}
    warning=None
    if cleanup_storage:
        try:storage=purge_project_prefix()
        except StorageError as exc:
            warning=str(exc)
            current_app.logger.error('library_reset_storage_cleanup_failed type=%s',type(exc).__name__)
    return {'reset':True,'before':inventory['counts'],'storage':storage,'warning':warning}

def _stage(p):
    name=(p.exam_type.name or '').strip().casefold();session=(p.session or '').strip().upper()
    if name=='quiz 1':return ('quiz1','Quiz 1',1)
    if name=='quiz 2':return ('quiz2','Quiz 2',2)
    if name=='end term' and session=='FN':return ('end_fn','End Term · FN',3)
    if name=='end term' and session=='AN':return ('end_an','End Term · AN',4)
    return ('other','Other / Practical',5)

def _paper_state(p,ready,latest):
    effective=p.canonical_paper_id or p.id
    if effective in ready:return 'available'
    job=latest.get(p.id)
    if job and job.status in ACTIVE:return 'queued'
    if job and job.status in FAILED:return 'failed'
    if p.status=='ARCHIVED':return 'ignored'
    return 'pending'

def campaign():
    papers=Paper.query.options(joinedload(Paper.exam_type),joinedload(Paper.term),joinedload(Paper.course)).filter(Paper.source_url.isnot(None)).all()
    ready={pid for pid, in db.session.query(Question.paper_id).filter(Question.status=='AVAILABLE').distinct()}
    latest_ids=db.session.query(func.max(IngestionFile.id)).group_by(IngestionFile.paper_id)
    latest={f.paper_id:f for f in IngestionFile.query.filter(IngestionFile.id.in_(latest_ids)).all()}
    grouped={}
    totals=defaultdict(int)
    for p in papers:
        key,label,rank=_stage(p);state=_paper_state(p,ready,latest)
        totals[state]+=1
        gkey=(rank,key,label,p.term.id,p.term.name,p.term.year,p.term.month)
        row=grouped.setdefault(gkey,{'stage':key,'label':label,'rank':rank,'term_id':p.term.id,'term':p.term.name,'year':p.term.year,'month':p.term.month,'total':0,'available':0,'pending':0,'queued':0,'failed':0,'ignored':0})
        row['total']+=1;row[state]+=1
    rows=sorted(grouped.values(),key=lambda x:(x['rank'],-x['year'],-x['month'],x['term']))
    for row in rows:
        row['finished']=row['available']+row['ignored']
        row['percent']=round((row['finished']/row['total'])*100,1) if row['total'] else 100
        row['complete']=row['pending']==0 and row['queued']==0 and row['failed']==0
    current=next((r for r in rows if not r['complete']),None)
    ready_count=totals['available'];total=len(papers)
    return {'total':total,'available':ready_count,'pending':totals['pending'],'queued':totals['queued'],'failed':totals['failed'],'ignored':totals['ignored'],
            'percent':round((ready_count/total)*100,1) if total else 0,'groups':rows,'current':current}

def group_papers(stage,term_id,state='pending'):
    papers=Paper.query.options(joinedload(Paper.exam_type),joinedload(Paper.term)).filter_by(term_id=term_id).filter(Paper.source_url.isnot(None)).order_by(Paper.id).all()
    ready={pid for pid, in db.session.query(Question.paper_id).filter(Question.status=='AVAILABLE').distinct()}
    latest_ids=db.session.query(func.max(IngestionFile.id)).group_by(IngestionFile.paper_id)
    latest={f.paper_id:f for f in IngestionFile.query.filter(IngestionFile.id.in_(latest_ids)).all()}
    return [p for p in papers if _stage(p)[0]==stage and _paper_state(p,ready,latest)==state]
