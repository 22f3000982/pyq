"""Admin corrections preserve question identity and temporary attempt snapshots."""
import copy,math,time,uuid
from pathlib import Path
from flask import request,jsonify,abort,g
from sqlalchemy import update
from .models import db,Question,QuestionOption,QuestionImage,QuestionReview,ContentReport,Paper,IngestionFile,IngestionBatch
from .api import require_user,body,paper_json
from .engine import question_snapshot,validate_question
from .storage import write_asset,publish

FIELDS=('number','kind','text','answers','answer_status','explanation','marks','negative_marks','tolerance','topic','status','evidence','warnings','source_page','source_pages')
def state(q):
    return {**{k:copy.deepcopy(getattr(q,k)) for k in FIELDS},'options':[{'key':o.key,'text':o.text} for o in q.options], 'images':[{'id':i.id,'path':i.path,'alt':i.alt,'option_key':i.option_key,'source_page':i.source_page} for i in q.images if (q.evidence or {}).get('_active_image_ids') is None or i.id in q.evidence['_active_image_ids']]}

def refresh_paper(q):
    p=db.session.get(Paper,q.paper_id)
    if p.status!='ARCHIVED':
        available=Question.query.filter_by(paper_id=p.id,status='AVAILABLE').count()
        failed=Question.query.filter_by(paper_id=p.id,status='EXTRACTION_FAILED').count()
        p.status=('PARTIALLY_AVAILABLE' if failed else 'AVAILABLE') if available else 'EXTRACTION_FAILED'
    return p

def audit(q,before,action):
    q.updated_at=time.time();db.session.add(QuestionReview(question_id=q.id,user_id=g.user.id,action=action,before=before,after=state(q)));refresh_paper(q)

def conflict(q,payload):
    db.session.execute(db.select(Paper).filter_by(id=q.paper_id).with_for_update()).scalar_one()
    db.session.refresh(q)
    if payload.get('updated_at')!=q.updated_at:abort(409,description='Question changed since you opened it. Reload before saving.')
    if IngestionFile.query.filter(IngestionFile.paper_id==q.paper_id,IngestionFile.status.in_(['QUEUED','FETCH_QUEUED','FETCHING','PROCESSING'])).first():abort(409,description='Wait for this paper to finish processing before editing.')

def apply(q,data):
    for k in FIELDS:
        if k in data:setattr(q,k,copy.deepcopy(data[k]))
    q.options=[];db.session.flush()
    q.options=[QuestionOption(key=o['key'],text=o['text'],position=n) for n,o in enumerate(data['options'])]
    q.evidence={**(q.evidence or {}),'_admin_locked':True,'_active_image_ids':[i['id'] for i in data['images']]}

def register_content_routes(admin):
    from .admin_api import admin_question,file_json
    @admin.get('/questions/<int:id>')
    @require_user(True)
    def question_detail(id):
        q=db.get_or_404(Question,id)
        return jsonify(question=admin_question(q),updated_at=q.updated_at,history=[{'id':h.id,'action':h.action,'created_at':h.created_at} for h in QuestionReview.query.filter_by(question_id=id).order_by(QuestionReview.id.desc()).limit(50)])

    @admin.patch('/questions/<int:id>')
    @require_user(True)
    def edit_question(id):
        q=db.session.execute(db.select(Question).filter_by(id=id).with_for_update()).scalar_one_or_none()
        if q is None:abort(404)
        b=body();conflict(q,b);before=state(q);data=state(q)
        for key in ('kind','text','answers','explanation','marks','negative_marks','tolerance','topic'):
            if key in b:data[key]=b[key]
        for key in ('text','explanation','topic'):
            v=data.get(key)
            if v is not None and (not isinstance(v,str) or len(v)>(20000 if key!='topic' else 150)):abort(400,description='Invalid '+key)
        passage=b.get('passage',question_snapshot(q).get('passage'))
        if passage is not None and (not isinstance(passage,str) or len(passage)>20000):abort(400,description='Invalid passage')
        data['evidence']={**data['evidence'],'shared_passage_text':passage or None,'subquestion_text':data['text'] if passage else None,'_admin_locked':True}
        options=b.get('options',data['options'])
        if not isinstance(options,list) or len(options)>20 or any(not isinstance(o,dict) or not isinstance(o.get('key'),str) or not 1<=len(o['key'])<=20 or not isinstance(o.get('text'),str) or not o['text'].strip() or len(o['text'])>10000 for o in options):abort(400,description='Invalid options')
        data['options']=[{'key':o['key'],'text':o['text']} for o in options]
        if len({o['key'] for o in options})!=len(options):abort(400,description='Option keys must be unique')
        for key in ('marks','negative_marks','tolerance'):
            v=data[key]
            if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or v<0):abort(400,description='Invalid '+key)
        data['answer_status']='ANSWER_AVAILABLE' if data['answers'] is not None else 'ANSWER_UNAVAILABLE'
        data['status']='HIDDEN' if q.status=='HIDDEN' else 'AVAILABLE'
        if q.status=='HIDDEN':data['evidence']['_admin_previous_status']='AVAILABLE'
        try:validate_question(data)
        except (ValueError,TypeError,KeyError) as exc:abort(400,description=str(exc))
        # A range/alternative NAT key must use the same validator as text input.
        if data['kind']=='NAT' and isinstance(data['answers'],dict) and data['answers']!=before['answers']:
            from .numeric import parse_numeric_key
            try:
                if parse_numeric_key(data['answers'].get('raw',''))!=data['answers']:raise ValueError()
            except (ValueError,TypeError,KeyError):abort(400,description='Use a numeric NAT answer or a valid source range key.')
        keep=b.get('image_ids',[i['id'] for i in data['images']])
        valid={i.id for i in q.images}
        if not isinstance(keep,list) or any(type(i)!=int or i not in valid for i in keep):abort(400,description='Invalid image selection')
        data['images']=[{'id':i.id} for i in q.images if i.id in keep]
        report=None
        if b.get('resolve_report_id') is not None:
            if type(b['resolve_report_id']) is not int:abort(400,description='Invalid report id')
            report=db.get_or_404(ContentReport,b['resolve_report_id'])
            if report.question_id!=q.id:abort(400,description='Report belongs to another question')
        apply(q,data);audit(q,before,'EDIT')
        if report:report.status='RESOLVED';report.resolved_at=time.time()
        db.session.commit();return jsonify(question=admin_question(q),updated_at=q.updated_at)

    @admin.post('/questions/<int:id>/visibility')
    @require_user(True)
    def visibility(id):
        q=db.session.execute(db.select(Question).filter_by(id=id).with_for_update()).scalar_one_or_none()
        if q is None:abort(404)
        b=body();conflict(q,b)
        if type(b.get('hidden')) is not bool:abort(400,description='Choose hide or restore')
        before=state(q);e={**(q.evidence or {}),'_admin_locked':True}
        if b['hidden']:
            if q.status!='HIDDEN':e['_admin_previous_status']=q.status
            q.status='HIDDEN'
        elif q.status=='HIDDEN':q.status=e.get('_admin_previous_status','AVAILABLE')
        q.evidence=e;audit(q,before,'HIDE' if b['hidden'] else 'RESTORE');db.session.commit()
        return jsonify(question=admin_question(q),updated_at=q.updated_at)

    @admin.post('/questions/<int:id>/undo')
    @require_user(True)
    def undo(id):
        q=db.session.execute(db.select(Question).filter_by(id=id).with_for_update()).scalar_one_or_none()
        if q is None:abort(404)
        b=body();conflict(q,b)
        h=QuestionReview.query.filter_by(question_id=id).order_by(QuestionReview.id.desc()).first()
        if not h or not h.before:abort(409,description='No correction to undo')
        before=state(q);apply(q,h.before);audit(q,before,'UNDO');db.session.commit()
        return jsonify(question=admin_question(q),updated_at=q.updated_at)

    @admin.post('/questions/<int:id>/images')
    @require_user(True)
    def upload_question_image(id):
        import fitz
        q=db.get_or_404(Question,id);conflict(q,{'updated_at':request.form.get('updated_at',type=float)})
        upload=request.files.get('file')
        if not upload:abort(400,description='Choose a PNG or JPEG image')
        data=upload.read(5*1024*1024+1)
        if len(data)>5*1024*1024:abort(400,description='Image must be under 5 MB')
        if data.startswith(b'\x89PNG\r\n\x1a\n'):ext='png'
        elif data.startswith(b'\xff\xd8\xff'):ext='jpg'
        else:abort(400,description='Only PNG/JPEG images are accepted')
        try:
            pix=fitz.Pixmap(data)
            if pix.width*pix.height>20000000:abort(400,description='Image dimensions are too large')
        except Exception:abort(400,description='Invalid image')
        option=request.form.get('option_key') or None
        if option and option not in {o.key for o in q.options}:abort(400,description='Invalid option key')
        before=state(q);path='admin-'+uuid.uuid4().hex+'.'+ext;write_asset(path,data);publish(path,verify=True)
        image=QuestionImage(question_id=q.id,path=path,option_key=option,alt='Admin corrected diagram',source_page=q.source_page);q.images.append(image);db.session.flush()
        q.evidence={**(q.evidence or {}),'_admin_locked':True,'_active_image_ids':[i['id'] for i in before['images']]+[image.id]}
        audit(q,before,'IMAGE');db.session.commit();return jsonify(question=admin_question(q),updated_at=q.updated_at),201

    @admin.post('/papers/<int:id>/replacement')
    @require_user(True)
    def replace_pdf(id):
        import hashlib
        from .ingestion import validate_pdf,update_batch
        from .acquisition import event
        from flask import current_app
        p=db.session.execute(db.select(Paper).filter_by(id=id).with_for_update()).scalar_one_or_none()
        if p is None:abort(404)
        if p.status=='ARCHIVED' or p.canonical_paper_id:abort(409,description='Restore this paper first, or replace its original canonical paper.')
        if IngestionFile.query.filter(IngestionFile.paper_id==id,IngestionFile.status.in_(['QUEUED','FETCH_QUEUED','FETCHING','PROCESSING'])).first():abort(409,description='This paper is already processing')
        upload=request.files.get('file')
        if not upload:abort(400,description='Choose a PDF')
        data=upload.read(current_app.config['MAX_UPLOAD_SIZE']+1)
        if len(data)>current_app.config['MAX_UPLOAD_SIZE']:abort(400,description='PDF exceeds upload limit')
        try:pages=validate_pdf(data)
        except Exception:abort(400,description='The file is not a readable, unencrypted PDF.')
        sha=hashlib.sha256(data).hexdigest();existing=IngestionFile.query.filter_by(file_hash=sha).first()
        path=sha+'.pdf';write_asset(path,data);publish(path,verify=True)
        batch=IngestionBatch(user_id=g.user.id);db.session.add(batch);db.session.flush()
        f=IngestionFile(batch_id=batch.id,paper_id=p.id,filename=(upload.filename or 'replacement.pdf')[:255],path=path,pages=pages,file_hash=None if existing else sha,status='QUEUED',source_url=p.source_url)
        db.session.add(f);db.session.flush();event(f,'REPLACEMENT','Corrected PDF uploaded for this existing paper; old content retained until extraction succeeds.')
        db.session.commit();update_batch(batch.id)
        return jsonify(file=file_json(f),paper=paper_json(p)),202

    @admin.post('/ingestion/<int:id>/process-now')
    @require_user(True)
    def process_now(id):
        from .ingestion import process_file,update_batch
        f=db.get_or_404(IngestionFile,id)
        if db.session.get(Paper,f.paper_id).status=='ARCHIVED':abort(409,description='Restore the archived paper before processing')
        if not f.path:abort(409,description='Upload a replacement PDF first')
        if not db.session.execute(update(IngestionFile).where(IngestionFile.id==id,IngestionFile.status=='QUEUED').values(status='PROCESSING',started_at=time.time())).rowcount:
            db.session.rollback();abort(409,description='Job is no longer queued. Refresh its status.')
        db.session.commit();process_file(id);update_batch(f.batch_id)
        return jsonify(file=file_json(db.session.get(IngestionFile,id)),paper=paper_json(db.session.get(Paper,f.paper_id)))
