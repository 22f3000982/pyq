from .storage import send_asset,ensure_local,publish,StorageError
import uuid,time,hashlib
from pathlib import Path
import fitz
from sqlalchemy import or_
from flask import Blueprint,jsonify,request,g,abort,current_app,send_from_directory
from .models import *
from .api import integer_argument,require_user,body,paginate,paginate_rows,paper_json,paper_rows,course_json,user_json,PAPER_LOAD
from .engine import question_snapshot,validate_question,aggregate
from .ingestion import store_upload,update_batch,root
admin=Blueprint('admin',__name__,url_prefix='/api/admin')

def admin_question(q):return {**question_snapshot(q),'status':q.status,'confidence':q.confidence,'warnings':q.warnings,'ingestion_file_id':q.ingestion_file_id}
def file_json(f):return {k:getattr(f,k) for k in ('id','batch_id','paper_id','filename','status','error','warnings','pages','extracted','retries','started_at','finished_at','source_url','events','duplicate_of_id')}

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

@admin.post('/catalog/preview')
@require_user(True)
def preview_catalog():
    from .catalog import preview_workbook
    path=_workbook_upload()
    try:return jsonify(preview_workbook(path))
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
        result=apply_sync(path,
            expected_hash=request.form.get('workbook_hash') or None,
            process_new=request.form.get('process_new','true').lower()=='true',
            process_unprocessed=request.form.get('process_unprocessed','true').lower()=='true',
            changed_keys=[str(x) for x in changed[:500]],
            queue=True)
        return jsonify(**result),202
    finally:path.unlink(missing_ok=True)

@admin.post('/catalog')
@require_user(True)
def import_catalog():
    # Backward-compatible immediate catalog-only import for older clients.
    from .catalog import import_workbook
    path=_workbook_upload()
    try:return jsonify(**import_workbook(path),batch_id=None,queued=0)
    finally:path.unlink(missing_ok=True)

@admin.get('/imports')
@require_user(True)
def imports():return jsonify(paginate(ImportRun.query.order_by(ImportRun.id.desc()),lambda r:{'id':r.id,'created_at':r.created_at,'report':r.report}))

@admin.get('/questions')
@require_user(True)
def questions():
    q=Question.query
    if request.args.get('paper_id'):q=q.filter_by(paper_id=integer_argument('paper_id'))
    if request.args.get('status'):q=q.filter_by(status=request.args['status'])
    return jsonify(paginate(q.order_by(Question.id),lambda q:{**admin_question(q),'evidence':q.evidence,'source_pages':q.source_pages}))

@admin.post('/process-catalog')
@require_user(True)
def process_catalog():
    from .acquisition import queue_catalog
    batch,count=queue_catalog(g.user.id,retry=body().get('retry',False))
    return jsonify(batch_id=batch,queued=count),202

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
    if not f.file_hash or not f.pages or not 1<=page<=f.pages:abort(404)
    name=f'{f.file_hash}-{page}.png'
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
