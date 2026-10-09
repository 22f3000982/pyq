from .storage import send_asset,ensure_local,publish,StorageError
import uuid,time,hashlib
from pathlib import Path
import fitz
from sqlalchemy import or_
from flask import Blueprint,jsonify,request,g,abort,current_app,send_from_directory,redirect
from .models import *
from .api import integer_argument,require_user,body,paginate,paginate_rows,paper_json,paper_rows,course_json,user_json,PAPER_LOAD
from .engine import question_snapshot,validate_question,aggregate
from .ingestion import store_upload,update_batch,root
admin=Blueprint('admin',__name__,url_prefix='/api/admin')

@admin.get('/analytics')
@require_user(True)
def analytics_report():
    from .analytics import report
    period=request.args.get('period','7d')
    if period not in ('today','7d','all'):abort(400,description='Choose today, 7d or all')
    return jsonify(report(period))

def admin_question(q):return {**question_snapshot(q),'status':q.status,'confidence':q.confidence,'warnings':q.warnings,'ingestion_file_id':q.ingestion_file_id,'hidden':q.status=='HIDDEN','manual_locked':bool((q.evidence or {}).get('_admin_locked'))}
def file_json(f):return {k:getattr(f,k) for k in ('id','batch_id','paper_id','filename','status','error','warnings','pages','extracted','retries','started_at','finished_at','source_url','events','duplicate_of_id')}

@admin.get('/google-drive/status')
@require_user(True)
def google_drive_status():
    from .google_drive import status
    return jsonify(status())

@admin.get('/google-drive/connect')
@require_user(True)
def google_drive_connect():
    from .google_drive import authorization_url
    try:return redirect(authorization_url())
    except RuntimeError as exc:abort(409,description=str(exc))

@admin.get('/google-drive/callback')
@require_user(True)
def google_drive_callback():
    from .google_drive import complete_callback
    try:complete_callback(request.args.get('code'),request.args.get('state'))
    except RuntimeError as exc:abort(400,description=str(exc))
    return redirect('/admin')

@admin.post('/google-drive/disconnect')
@require_user(True)
def google_drive_disconnect():
    from .google_drive import disconnect
    return jsonify(disconnect())

@admin.get('/stats')
@require_user(True)
def stats():
    from .ingestion import SUCCESS,FAILURES
    queued=IngestionFile.query.filter(IngestionFile.status.in_(['QUEUED','FETCH_QUEUED'])).count()
    active_processing=IngestionFile.query.filter(IngestionFile.status.in_(['PROCESSING','FETCHING'])).count()
    return jsonify(courses=Course.query.count(),papers=Paper.query.count(),questions=Question.query.filter_by(status='AVAILABLE').count(),processed=IngestionFile.query.filter(IngestionFile.status.in_(SUCCESS)).count(),queued=queued,active_processing=active_processing,processing=queued+active_processing,failed=IngestionFile.query.filter(IngestionFile.status.in_(FAILURES)).count(),flagged_questions=Question.query.filter_by(status='EXTRACTION_FAILED').count(),active_sessions=Attempt.query.filter_by(status='ACTIVE').count(),progress_records=PaperProgress.query.count(),users=User.query.filter_by(active=True).count())


@admin.post('/courses')
@require_user(True)
def add_course():
    b=body()
    if not b.get('name') or not b.get('code'):abort(400,description='Name and code required')
    c=Course(name=str(b['name'])[:200],code=str(b['code'])[:40],level=str(b.get('level',''))[:40],course_type=str(b.get('course_type',''))[:40]);db.session.add(c);db.session.commit();return jsonify(course_json(c)),201

@admin.get('/papers')
@require_user(True)
def list_papers():
    q=Paper.query.options(*PAPER_LOAD)
    if request.args.get('course_id'):q=q.filter(Paper.course_id==integer_argument('course_id'))
    if request.args.get('status'):q=q.filter(Paper.status==request.args['status'][:32])
    term=request.args.get('q','').strip()[:150]
    if term:
        like='%'+term+'%'
        q=q.join(Course).join(Term).join(ExamType).filter(or_(Paper.name.ilike(like),Course.name.ilike(like),Course.code.ilike(like),Term.name.ilike(like),ExamType.name.ilike(like)))
    return jsonify(paginate_rows(q.order_by(Paper.id.desc()),paper_rows))

@admin.post('/papers')
@require_user(True)
def add_paper():
    b=body();db.get_or_404(Course,b.get('course_id'))
    term=db.get_or_404(Term,b.get('term_id'));exam=db.get_or_404(ExamType,b.get('exam_type_id'))
    if not b.get('name'):abort(400,description='Name required')
    p=Paper(identity=uuid.uuid4().hex,course_id=b['course_id'],term_id=term.id,exam_type_id=exam.id,name=str(b['name'])[:300],session=str(b.get('session',''))[:20]);db.session.add(p);db.session.commit();return jsonify(paper_json(p)),201

@admin.post('/metadata')
@require_user(True)
def add_metadata():
    b=body()
    if b.get('kind')=='term':
        year=int(b.get('year',0));month=int(b.get('month',0))
        if not 2000<=year<=2100 or not 1<=month<=12:abort(400,description='Invalid term year/month')
        item=Term(name=str(b.get('name','')).strip()[:80],year=year,month=month)
    elif b.get('kind')=='exam':item=ExamType(name=str(b.get('name','')).strip()[:80])
    else:abort(400)
    if not item.name:abort(400)
    db.session.add(item);db.session.commit();return jsonify(id=item.id),201

@admin.patch('/papers/<int:id>')
@require_user(True)
def edit_paper(id):
    p=db.get_or_404(Paper,id);b=body()
    if 'duration_seconds' in b:
        if b['duration_seconds'] in (None,''):p.duration_seconds=None
        else:
            try:duration=int(b['duration_seconds'])
            except (TypeError,ValueError):abort(400,description='Duration must be a number of seconds')
            if not 30<=duration<=28800:abort(400,description='Duration must be between 30 seconds and 8 hours')
            p.duration_seconds=duration
    if 'name' in b:
        name=str(b['name']).strip()
        if not name:abort(400,description='Name required')
        p.name=name[:300]
    if 'session' in b:p.session=str(b['session'] or '')[:20]
    if 'source_url' in b:p.source_url=str(b['source_url']).strip()[:4000] if b['source_url'] else None
    if 'course_id' in b:
        db.get_or_404(Course,b['course_id']);p.course_id=b['course_id']
    if 'term_id' in b:
        db.get_or_404(Term,b['term_id']);p.term_id=b['term_id']
    if 'exam_type_id' in b:
        db.get_or_404(ExamType,b['exam_type_id']);p.exam_type_id=b['exam_type_id']
    db.session.commit();return jsonify(paper_json(p))

@admin.post('/papers/<int:id>/archive')
@require_user(True)
def archive_paper(id):
    p=db.get_or_404(Paper,id)
    if p.status=='ARCHIVED':return jsonify(paper=paper_json(p),archived=True)
    meta=dict(p.source_metadata or {});meta['_admin_archived_from']=p.status or 'CATALOG_ONLY'
    p.source_metadata=meta;p.status='ARCHIVED'
    paused=IngestionFile.query.filter(IngestionFile.paper_id==id,IngestionFile.status.in_(['QUEUED','FETCH_QUEUED'])).all()
    batch_ids={f.batch_id for f in paused}
    for f in paused:f.status='PAUSED';f.error='Paused because the paper was archived by an administrator.'
    db.session.commit()
    for batch_id in batch_ids:update_batch(batch_id)
    return jsonify(paper=paper_json(p),archived=True)

@admin.post('/papers/<int:id>/restore')
@require_user(True)
def restore_paper(id):
    p=db.get_or_404(Paper,id)
    if p.status!='ARCHIVED':return jsonify(paper=paper_json(p),archived=False)
    meta=dict(p.source_metadata or {});previous=meta.pop('_admin_archived_from','CATALOG_ONLY')
    p.source_metadata=meta;p.status=previous if previous!='ARCHIVED' else 'CATALOG_ONLY';db.session.commit()
    return jsonify(paper=paper_json(p),archived=False)

@admin.delete('/papers/<int:id>')
@require_user(True)
def delete_paper(id):
    p=db.get_or_404(Paper,id)
    dependencies={
        'questions':Question.query.filter_by(paper_id=id).count(),
        'imports':IngestionFile.query.filter_by(paper_id=id).count(),
        'attempts':Attempt.query.filter_by(paper_id=id).count(),
        'progress':PaperProgress.query.filter_by(paper_id=id).count(),
        'aliases':Paper.query.filter_by(canonical_paper_id=id).count(),
    }
    blockers={k:v for k,v in dependencies.items() if v}
    if blockers:
        abort(409,description='This paper has linked data and cannot be permanently deleted safely. Archive it instead. Linked: '+', '.join(f'{k}={v}' for k,v in blockers.items()))
    # Workbook provenance belongs to an otherwise-empty catalog entry and can be
    # removed together with it; processed/imported content is intentionally blocked.
    SourceEntry.query.filter_by(paper_id=id).delete(synchronize_session=False)
    db.session.delete(p);db.session.commit()
    return jsonify(deleted=True,id=id)

def _workbook_upload():
    upload=request.files.get('file')
    if not upload or not upload.filename.lower().endswith('.xlsx'):abort(400,description='Select an XLSX workbook')
    data=upload.read(10*1024*1024+1)
    if len(data)>10*1024*1024:abort(413)
    import io,zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist())>100*1024*1024:abort(413)
    except zipfile.BadZipFile:abort(400,description='Invalid workbook')
    path=root()/(uuid.uuid4().hex+'.xlsx');path.write_bytes(data)
    return path

def _catalog_level():
    level=request.form.get('level') or None
    if level is not None and level not in ('Degree','Diploma','Foundation'):
        abort(400,description='Choose Degree, Diploma or Foundation')
    return level

@admin.post('/catalog/preview')
@require_user(True)
def preview_catalog():
    from .catalog import preview_workbook
    path=_workbook_upload()
    try:return jsonify(preview_workbook(path,_catalog_level()))
    finally:path.unlink(missing_ok=True)

@admin.post('/catalog/apply')
@require_user(True)
def apply_catalog():
    from .catalog import apply_sync
    import json
    path=_workbook_upload()
    try:
        changed=json.loads(request.form.get('changed_keys','[]'))
        if not isinstance(changed,list):abort(400,description='changed_keys must be a list')
        try:batch_limit=int(request.form.get('batch_limit','20'))
        except ValueError:abort(400,description='batch_limit must be a number')
        if not 1<=batch_limit<=50:abort(400,description='batch_limit must be between 1 and 50')
        result=apply_sync(path,
            expected_hash=request.form.get('workbook_hash') or None,
            process_new=request.form.get('process_new','true').lower()=='true',
            process_unprocessed=request.form.get('process_unprocessed','true').lower()=='true',
            changed_keys=[str(x) for x in changed[:500]],
            queue=True,batch_limit=batch_limit,level=_catalog_level())
        return jsonify(**result),202
    finally:path.unlink(missing_ok=True)

@admin.post('/catalog')
@require_user(True)
def import_catalog():
    # Backward-compatible immediate catalog-only import for older clients.
    from .catalog import import_workbook
    path=_workbook_upload()
    try:return jsonify(**import_workbook(path,_catalog_level()),batch_id=None,queued=0)
    finally:path.unlink(missing_ok=True)

@admin.post('/catalog/refresh')
@require_user(True)
def refresh_master_catalog():
    """Import the entire workbook as catalog metadata only. Nothing is queued."""
    from .catalog import import_workbook
    path=_workbook_upload()
    try:
        result=import_workbook(path,_catalog_level())
        return jsonify(**result,queued=0,note='Master catalog refreshed. No papers were queued.'),201
    finally:path.unlink(missing_ok=True)

@admin.get('/catalog/campaign')
@require_user(True)
def catalog_campaign():
    from .library_campaign import campaign
    return jsonify(campaign(request.args.get('level') or None))

@admin.post('/catalog/campaign/process')
@require_user(True)
def process_campaign_group():
    from .library_campaign import campaign,group_papers
    from .acquisition import queue_catalog
    payload=body();overview=campaign(payload.get('level')); current=overview.get('current')
    if not current:abort(409,description='The catalog campaign is already complete.')
    stage=str(payload.get('stage') or current['stage'])
    try:term_id=int(payload.get('term_id') or current['term_id']);limit=int(payload.get('limit',20))
    except (TypeError,ValueError):abort(400,description='Invalid campaign batch request')
    if not 1<=limit<=20:abort(400,description='Campaign batches are limited to 1–20 papers')
    target=next((g for g in overview['groups'] if g['stage']==stage and g['term_id']==term_id),None)
    if target is None:abort(400,description='Unknown campaign term or assessment.')
    papers=group_papers(stage,term_id,'pending',payload.get('level'))
    ids=[p.id for p in papers[:limit]]
    if not ids:return jsonify(batch_id=None,queued=0,current=target,note='No pending papers in the selected target.'),200
    batch,count=queue_catalog(g.user.id,retry=False,limit=limit,paper_ids=ids)
    return jsonify(batch_id=batch,queued=count,current=target),202

@admin.post('/catalog/campaign/retry-failed')
@require_user(True)
def retry_campaign_failed():
    from .library_campaign import campaign,group_papers
    from .acquisition import queue_catalog
    payload=body();current=campaign(payload.get('level')).get('retry_target')
    if not current:abort(409,description='There are no failed campaign papers to retry.')
    try:limit=int(payload.get('limit',20))
    except (TypeError,ValueError):abort(400,description='Invalid retry limit')
    if not 1<=limit<=20:abort(400,description='Retry batches are limited to 1–20 papers')
    papers=group_papers(current['stage'],current['term_id'],'failed',payload.get('level'))
    ids=[p.id for p in papers[:limit]]
    if not ids:return jsonify(batch_id=None,queued=0,note='No failed papers in the current target.'),200
    batch,count=queue_catalog(g.user.id,retry=True,limit=limit,paper_ids=ids)
    return jsonify(batch_id=batch,queued=count,current=current),202

@admin.get('/library-reset/preview')
@require_user(True)
def library_reset_preview():
    from .library_campaign import library_inventory
    return jsonify(**library_inventory(include_storage=True),confirmation='RESET PYQ LIBRARY')

@admin.post('/library-reset')
@require_user(True)
def library_reset():
    from .library_campaign import reset_library
    payload=body()
    if payload.get('confirmation')!='RESET PYQ LIBRARY':
        abort(400,description='Type RESET PYQ LIBRARY exactly to confirm.')
    try:return jsonify(reset_library(g.user.id,cleanup_storage=payload.get('cleanup_storage',True),cancel_active=payload.get('cancel_active',False)))
    except RuntimeError as exc:abort(409,description=str(exc))

@admin.get('/catalog/batches/latest')
@require_user(True)
def latest_catalog_batch():
    from .ingestion import SUCCESS,FAILURES
    batch=(IngestionBatch.query.join(IngestionFile,IngestionFile.batch_id==IngestionBatch.id)
           .filter(IngestionFile.status.in_(['FETCH_QUEUED','QUEUED','FETCHING','PROCESSING']))
           .order_by(IngestionBatch.id.desc()).first())
    if not batch:return jsonify(batch_id=None)
    return jsonify(batch_id=batch.id)

@admin.post('/catalog/files/<int:id>/retry')
@require_user(True)
def retry_catalog_file(id):
    from .acquisition import queue_catalog
    item=db.get_or_404(IngestionFile,id)
    if item.status not in ('PROCESSING_FAILED','EXTRACTION_FAILED'):
        abort(409,description='Only failed papers can be retried.')
    batch,count=queue_catalog(g.user.id,retry=True,limit=1,paper_ids=[item.paper_id])
    return jsonify(batch_id=batch,queued=count),202

@admin.post('/catalog/files/<int:id>/recover')
@require_user(True)
def recover_catalog_file(id):
    from .ingestion import update_batch
    item=db.get_or_404(IngestionFile,id)
    if item.status not in ('FETCHING','PROCESSING'):
        abort(409,description='This paper is no longer active. Refresh its status.')
    if item.started_at and item.started_at>time.time()-1800:
        abort(409,description='This paper may still be running. Recovery is available 30 minutes after it started; you can process another batch meanwhile.')
    item.status='PROCESSING_FAILED';item.finished_at=time.time()
    item.error='Interrupted processing recovered by admin. Retry this paper to download and extract again.'
    paper=db.session.get(Paper,item.paper_id)
    if not Question.query.filter_by(paper_id=paper.id,status='AVAILABLE').count():paper.status='PROCESSING_FAILED'
    db.session.commit();update_batch(item.batch_id)
    return jsonify(recovered=True,paper_id=item.paper_id)

@admin.post('/catalog/batches/<int:id>/run-next')
@require_user(True)
def run_catalog_batch_next(id):
    """Free-plan runner: do exactly one paper synchronously on the web service."""
    from .acquisition import download_one
    from .ingestion import process_one,SUCCESS,FAILURES,update_batch
    batch=db.get_or_404(IngestionBatch,id)
    # Recover a request that died mid-paper (browser/network/server restart).
    stale_before=time.time()-1800
    for stale in IngestionFile.query.filter_by(batch_id=id).filter(
        IngestionFile.status.in_(['FETCHING','PROCESSING']),or_(IngestionFile.started_at.is_(None),IngestionFile.started_at<stale_before)
    ):
        stale.status='QUEUED' if stale.path else 'FETCH_QUEUED'
        stale.error='Previous on-demand processing request expired; safely resumed.'
        stale.started_at=None
    db.session.commit()
    record=(IngestionFile.query.filter_by(batch_id=id)
            .filter(IngestionFile.status.in_(['FETCH_QUEUED','QUEUED']))
            .order_by(IngestionFile.id).first())
    if record:
        if record.status=='FETCH_QUEUED':download_one(record.id)
        record=db.session.get(IngestionFile,record.id)
        if record and record.status=='QUEUED':process_one(record.id)
        update_batch(id)
    files=IngestionFile.query.filter_by(batch_id=id).order_by(IngestionFile.id).all()
    total=len(files);success=sum(f.status in SUCCESS for f in files);failed=sum(f.status in FAILURES for f in files)
    active=sum(f.status in ('FETCHING','PROCESSING') for f in files)
    queued=sum(f.status in ('FETCH_QUEUED','QUEUED') for f in files)
    finished=success+failed;percent=round((finished/total)*100,1) if total else 100
    return jsonify(id=id,status=batch.status,total=total,completed=success,failed=failed,active=active,queued=queued,
                   finished=finished,percent=percent,done=(total==0 or finished==total),
                   items=[{'id':f.id,'paper_id':f.paper_id,'filename':f.filename,'status':f.status,'error':f.error,'extracted':f.extracted,'elapsed_seconds':max(0,int(time.time()-f.started_at)) if f.started_at else None,'recoverable':f.status in ('FETCHING','PROCESSING') and (not f.started_at or f.started_at<time.time()-1800)} for f in files])

@admin.get('/catalog/batches/<int:id>')
@require_user(True)
def catalog_batch(id):
    from .ingestion import SUCCESS,FAILURES
    batch=db.get_or_404(IngestionBatch,id)
    files=IngestionFile.query.filter_by(batch_id=id).order_by(IngestionFile.id).all()
    total=len(files);success=sum(f.status in SUCCESS for f in files);failed=sum(f.status in FAILURES for f in files)
    active=sum(f.status in ('FETCHING','PROCESSING') for f in files)
    queued=sum(f.status in ('FETCH_QUEUED','QUEUED') for f in files)
    finished=success+failed
    percent=round((finished/total)*100,1) if total else 100
    return jsonify(id=id,status=batch.status,total=total,completed=success,failed=failed,active=active,queued=queued,
                   finished=finished,percent=percent,done=(total==0 or finished==total),
                   items=[{'id':f.id,'paper_id':f.paper_id,'filename':f.filename,'status':f.status,'error':f.error,'extracted':f.extracted,'elapsed_seconds':max(0,int(time.time()-f.started_at)) if f.started_at else None,'recoverable':f.status in ('FETCHING','PROCESSING') and (not f.started_at or f.started_at<time.time()-1800)} for f in files])

@admin.get('/imports')
@require_user(True)
def imports():return jsonify(paginate(ImportRun.query.order_by(ImportRun.id.desc()),lambda r:{'id':r.id,'created_at':r.created_at,'report':r.report}))

@admin.get('/questions')
@require_user(True)
def questions():
    q=Question.query
    if request.args.get('paper_id'):q=q.filter_by(paper_id=integer_argument('paper_id'))
    if request.args.get('status'):q=q.filter_by(status=request.args['status'])
    else:q=q.filter(Question.status!='SUPERSEDED')
    return jsonify(paginate(q.order_by(Question.id),lambda q:{**admin_question(q),'evidence':q.evidence,'source_pages':q.source_pages}))

@admin.post('/process-catalog')
@require_user(True)
def process_catalog():
    from .acquisition import queue_catalog
    payload=body()
    try:limit=int(payload.get('limit',20))
    except (TypeError,ValueError):abort(400,description='limit must be a number')
    if not 1<=limit<=50:abort(400,description='limit must be between 1 and 50')
    batch,count=queue_catalog(g.user.id,retry=payload.get('retry',False),limit=limit)
    return jsonify(batch_id=batch,queued=count,limit=limit),202

@admin.post('/papers/upload')
@admin.post('/papers/bulk-upload')
@require_user(True)
def upload():
    files=request.files.getlist('files')
    if not files or len(files)>20:abort(400,description='Choose 1–20 PDF files')
    # Each file explicitly targets an existing catalog paper; no duplicate metadata guessing.
    import json
    try:ids=json.loads(request.form.get('paper_ids','[]'))
    except ValueError:abort(400)
    if len(ids)!=len(files):abort(400,description='Map each file to one paper')
    papers=[db.get_or_404(Paper,id) for id in ids]
    batch=IngestionBatch(user_id=g.user.id);db.session.add(batch);db.session.commit()
    records=[store_upload(f,p,batch,request.form.get('replace')=='true') for f,p in zip(files,papers)]
    update_batch(batch.id);return jsonify(batch_id=batch.id,files=[file_json(f) for f in records]),202

@admin.post('/upload-pyq')
@require_user(True)
def upload_pyq():
    course=db.get_or_404(Course,request.form.get('course_id',type=int))
    exam=db.get_or_404(ExamType,request.form.get('exam_type_id',type=int))
    term=db.get_or_404(Term,request.form.get('term_id',type=int))
    upload=request.files.get('file')
    if not upload:abort(400,description='Choose a PDF')
    name=(request.form.get('name') or Path(upload.filename or 'Paper').stem).strip()[:300]
    # Repeated upload of the same name/metadata reuses the paper; byte hashes deduplicate content.
    paper=Paper.query.filter_by(course_id=course.id,exam_type_id=exam.id,term_id=term.id,name=name).first()
    if not paper:
        paper=Paper(identity=uuid.uuid4().hex,course_id=course.id,exam_type_id=exam.id,term_id=term.id,name=name)
        db.session.add(paper)
    batch=IngestionBatch(user_id=g.user.id);db.session.add(batch);db.session.flush()
    record=store_upload(upload,paper,batch)
    update_batch(batch.id)
    return jsonify(file=file_json(record),paper=paper_json(paper)),202

@admin.get('/ingestion/<int:id>')
@require_user(True)
def ingestion_detail(id):
    record=db.get_or_404(IngestionFile,id)
    paper=db.get_or_404(Paper,record.paper_id)
    effective=db.session.get(Paper,paper.canonical_paper_id) if paper.canonical_paper_id else paper
    result=file_json(record)
    if record.duplicate_of_id:
        canonical=db.session.get(IngestionFile,record.duplicate_of_id)
        result['effective_status']=canonical.status
        result['events']=canonical.events
        result['error']=canonical.error
    else:result['effective_status']=record.status
    return jsonify(file=result,paper=paper_json(paper))

@admin.get('/ingestion')
@require_user(True)
def ingestion():return jsonify(paginate(IngestionFile.query.order_by(IngestionFile.id.desc()),file_json))

@admin.post('/ingestion/<int:id>/retry')
@require_user(True)
def retry(id):
    f=db.get_or_404(IngestionFile,id)
    if f.status not in ('PROCESSING_FAILED','EXTRACTION_FAILED'):abort(409,description='Only failed processing jobs can be retried')
    if not f.path and not f.source_url:abort(409,description='Invalid uploaded bytes; upload a corrected PDF')
    if f.path:
        try:ensure_local(f.path)
        except (FileNotFoundError,StorageError):abort(409,description='The stored PDF is missing. Please choose the PDF and upload it again.')
    f.status='QUEUED' if f.path else 'FETCH_QUEUED';f.error=None;f.retries+=1;f.started_at=None;f.finished_at=None;db.session.commit();update_batch(f.batch_id);return jsonify(file_json(f))

@admin.get('/ingestion/<int:id>/source')
@require_user(True)
def source(id):
    f=db.get_or_404(IngestionFile,id)
    if not f.path:abort(404)
    return send_asset(f.path,mimetype='application/pdf')

@admin.get('/ingestion/<int:id>/pages/<int:page>')
@require_user(True)
def source_page(id,page):
    f=db.get_or_404(IngestionFile,id)
    if not f.path or not f.pages or not 1<=page<=f.pages:abort(404)
    source_hash=f.file_hash or hashlib.sha256(ensure_local(f.path).read_bytes()).hexdigest()
    name=f'{source_hash}-{page}.png'
    if not (root()/name).exists():
        with fitz.open(ensure_local(f.path)) as doc:doc[page-1].get_pixmap(matrix=fitz.Matrix(1.4,1.4)).save(root()/name)
    return send_asset(name,mimetype='image/png')

@admin.get('/users')
@require_user(True)
def users():return jsonify(paginate(User.query.order_by(User.id),lambda u:{**user_json(u),'active':u.active}))

@admin.patch('/users/<int:id>')
@require_user(True)
def edit_user(id):
    u=db.get_or_404(User,id);b=body()
    if id==g.user.id:abort(409,description='You cannot disable your own account')
    if not isinstance(b.get('active'),bool):abort(400)
    u.active=b['active'];db.session.commit();return jsonify(active=u.active)

@admin.get('/settings')
@require_user(True)
def settings():return jsonify(llm_provider=current_app.config['LLM_PROVIDER'],llm_model=current_app.config['LLM_MODEL'],llm_configured=bool(current_app.config['LLM_API_KEY']),max_upload_size=current_app.config['MAX_UPLOAD_SIZE'],ocr=current_app.config['OCR_ENABLED'])

@admin.get('/manual-grading')
@require_user(True)
def grading_queue():
    return jsonify(items=[],total=0,note='Historical question responses are not retained; source-only automatic scoring is used.')

@admin.post('/manual-grading/<int:id>')
@require_user(True)
def manual_grade(id):
    abort(410,description='Historical manual grading is disabled. Only the latest source-scored paper percentage is retained.')


def report_json(r):
    q=db.session.get(Question,r.question_id);p=db.session.get(Paper,q.paper_id)
    return {'id':r.id,'question_id':q.id,'number':q.number,'paper_id':p.id,'paper':p.name,'issue':r.issue,'description':r.description,'status':r.status,'created_at':r.created_at,'resolved_at':r.resolved_at}

@admin.get('/content-reports')
@require_user(True)
def content_reports():
    status=request.args.get('status','OPEN')
    if status not in ('OPEN','RESOLVED','ALL'):abort(400,description='Invalid report status.')
    query=ContentReport.query
    if status!='ALL':query=query.filter_by(status=status)
    return jsonify(paginate(query.order_by(ContentReport.created_at.desc()),report_json))

@admin.get('/content-reports/<int:id>')
@require_user(True)
def content_report_detail(id):
    r=db.get_or_404(ContentReport,id)
    return jsonify(**report_json(r),question=admin_question(db.session.get(Question,r.question_id)))

@admin.patch('/content-reports/<int:id>')
@require_user(True)
def update_content_report(id):
    r=db.get_or_404(ContentReport,id);payload=body();status=payload.get('status')
    if status not in ('OPEN','RESOLVED'):abort(400,description='Invalid report status.')
    hide=payload.get('hide_question',False)
    if type(hide) is not bool or (hide and status!='RESOLVED'):abort(400,description='Hide requires a resolved report.')
    if hide:
        from .admin_content import conflict,state,audit
        q=db.session.execute(db.select(Question).filter_by(id=r.question_id).with_for_update()).scalar_one_or_none()
        if q is None:abort(404)
        conflict(q,payload)
        if q.status!='HIDDEN':
            before=state(q)
            q.evidence={**(q.evidence or {}),'_admin_locked':True,'_admin_previous_status':q.status}
            q.status='HIDDEN';audit(q,before,'HIDE')
    r.status=status;r.resolved_at=time.time() if status=='RESOLVED' else None
    db.session.commit();return jsonify(report_json(r))

from .admin_content import register_content_routes
register_content_routes(admin)
