from .storage import send_asset,image_url,StorageError
import time
from flask import Blueprint,jsonify,request,g,abort,current_app,send_from_directory,redirect
from sqlalchemy import insert
from sqlalchemy.orm import selectinload,joinedload
from .models import *
from . import limiter
from .api import integer_argument,require_visitor,body,paginate,visible_papers
from .engine import *
from .performance import span
exams=Blueprint('exams',__name__,url_prefix='/api')

def owned(id):
    a=db.get_or_404(Attempt,id)
    if a.guest_hash!=g.guest_hash:abort(404)
    expire_attempt(a)
    if a.expires_at<=time.time():
        cleanup_sessions(guest_hash=g.guest_hash);abort(410,description='This temporary session has expired. Your latest paper score is retained; you can retake the paper.')
    return a

def attempt_json(a):return {'id':a.id,'paper_id':a.paper_id,'title':a.title,'mode':a.mode,'status':a.status,'started_at':a.started_at,'deadline':a.deadline,'submitted_at':a.submitted_at,'server_time':time.time(),'result':a.result,'expires_at':a.expires_at,'records_progress':a.records_progress,'palette':[{'question_id':i.question_id,'number':i.snapshot['number'],'state':palette_state(i),'visited':i.visited,'marked':i.marked} for i in sorted(a.items,key=lambda i:(i.snapshot.get("paper_id",0),question_order(i.snapshot["number"]),i.position))]}

def attempt_status_json(a):
    # Deliberately excludes a.items/snapshots. This endpoint is used for the
    # occasional timer safety sync and stays O(1) in paper question count.
    return {'id':a.id,'status':a.status,'deadline':a.deadline,'submitted_at':a.submitted_at,
            'server_time':time.time(),'expires_at':a.expires_at,'version':a.version}

def attempt_image_ttl(a):
    # Bootstrap contains URLs for the whole paper. Keep them valid for the
    # remaining temporary attempt lifetime so late questions do not fall back
    # through Flask after the old 10-minute signature expired.
    remaining=max(0,(a.expires_at or time.time()+3600)-time.time())
    return max(600,min(604799,int(remaining)+300))

def use_paper_image_delivery(paper_id):
    """Use direct signed R2 URLs only for papers whose image set was verified."""
    if current_app.config.get('IMAGE_DELIVERY')!='signed':
        g.force_proxy_images=False;return
    if not paper_id:
        # Mixed collections can span old imports, so choose the reliable path.
        g.force_proxy_images=True;return
    paper=db.session.get(Paper,paper_id)
    meta=(paper.source_metadata or {}) if paper else {}
    g.force_proxy_images=not bool(meta.get('question_assets_verified_r2'))

def question_with_image_urls(snapshot):
    result=public_question(snapshot)
    paths=getattr(g,'image_paths',{})
    ttl=getattr(g,'image_signed_ttl',None)
    force_proxy=getattr(g,'force_proxy_images',False)
    result['images']=[{**image,'url':('/api/images/'+str(image['id'])+'?proxy=1') if force_proxy else (image_url(paths.get(image['id']),image['id'],expires=ttl) if paths.get(image['id']) else '/api/images/'+str(image['id'])+'?proxy=1')} for image in result.get('images',[]) if image.get('id') is not None]
    return result

def prepare_image_paths(snapshots,signed_ttl=None):
    if signed_ttl is not None:g.image_signed_ttl=signed_ttl
    if getattr(g,'force_proxy_images',False) or current_app.config.get('IMAGE_DELIVERY','proxy')=='proxy':return
    paths={}
    missing=set()
    for snapshot in snapshots:
        for image in snapshot.get('images',[]):
            if image.get('_asset_path'):paths[image['id']]=image['_asset_path']
            else:missing.add(image['id'])
    if missing:paths.update(db.session.query(QuestionImage.id,QuestionImage.path).filter(QuestionImage.id.in_(missing)).all())
    g.image_paths=paths

def bootstrap_json(a):
    items=sorted(a.items,key=lambda i:(i.snapshot.get('paper_id',0),question_order(i.snapshot['number']),i.position))
    use_paper_image_delivery(a.paper_id)
    prepare_image_paths([i.snapshot for i in items],attempt_image_ttl(a))
    bookmarks=set()
    return {**attempt_json(a),'items':[item_json(a,i,bookmarks) for i in items]}

def start_response(a):
    # Legacy helper for continuation flows that already own ORM answer objects.
    return jsonify(bootstrap_json(a) if request.args.get('bootstrap')=='1' else attempt_json(a)),201

def start_payload(a,snapshots,images_prepared=False):
    """Build a newly-created attempt response without re-reading its answer rows."""
    ordered=sorted(snapshots,key=lambda s:(s.get('paper_id',0),question_order(s['number']),s['id']))
    palette=[{'question_id':s['id'],'number':s['number'],'state':'NOT_VISITED','visited':False,'marked':False} for s in ordered]
    result={'id':a.id,'paper_id':a.paper_id,'title':a.title,'mode':a.mode,'status':a.status,
            'started_at':a.started_at,'deadline':a.deadline,'submitted_at':a.submitted_at,
            'server_time':time.time(),'result':a.result,'expires_at':a.expires_at,
            'records_progress':a.records_progress,'palette':palette}
    if request.args.get('bootstrap')=='1':
        if not images_prepared:
            use_paper_image_delivery(a.paper_id)
            prepare_image_paths(ordered,attempt_image_ttl(a))
        qids=[s['id'] for s in ordered]
        bookmarks=set()
        result['items']=[{'question':question_with_image_urls(s),'answer':None,'marked':False,
                          'visited':False,'status':a.status,'bookmarked':s['id'] in bookmarks}
                         for s in ordered]
    return result

def finish_new_attempt(a,snapshots):
    """Persist all answer rows in one batch and return the already-built bootstrap."""
    # A new start replaces this visitor's unfinished tests, even with answers.
    old_ids=db.session.query(Attempt.id).filter_by(guest_hash=g.guest_hash,status='ACTIVE')
    db.session.query(AttemptAnswer).filter(AttemptAnswer.attempt_id.in_(old_ids)).delete(synchronize_session=False)
    Attempt.query.filter_by(guest_hash=g.guest_hash,status='ACTIVE').delete(synchronize_session=False)
    with span('attempt_insert'):
        db.session.add(a);db.session.flush()
    with span('answer_insert'):
        db.session.execute(insert(AttemptAnswer),[
            {'attempt_id':a.id,'question_id':s['id'],'position':n,'snapshot':s,
             'visited':False,'response_touched':False,'marked':False}
            for n,s in enumerate(snapshots)
        ])
    # Resolve DB-backed delivery metadata before releasing the transaction.
    if request.args.get('bootstrap')=='1':
        with span('image_metadata'):
            use_paper_image_delivery(a.paper_id)
            prepare_image_paths(snapshots,attempt_image_ttl(a))
    from types import SimpleNamespace
    state=SimpleNamespace(**{name:getattr(a,name) for name in (
        'id','paper_id','title','mode','status','started_at','deadline',
        'submitted_at','result','expires_at','records_progress')})
    with span('commit'):
        db.session.commit()
    # Signing/serializing all images must not occupy a pooled DB connection.
    with span('bootstrap'):
        response=jsonify(start_payload(state,snapshots,images_prepared=True))
    return response,201

def item_json(a,i,bookmarks):
    result={'question':question_with_image_urls(i.snapshot),'answer':i.answer,'marked':i.marked,'visited':i.visited,'status':a.status,'bookmarked':i.question_id in bookmarks}
    if a.status!='ACTIVE' or (a.mode=='practice' and i.answer is not None):
        result['feedback']={**grade(i.snapshot,i.answer),'answers':i.snapshot['answers'],'explanation':i.snapshot['explanation'],'answer_status':i.snapshot['answer_status']}
    return result

def collection_query(kind):
    q=Question.query.filter(Question.status=='AVAILABLE',Question.paper_id.in_(visible_papers(Paper.query).with_entities(Paper.id)))
    if kind=='bookmarks':abort(410,description='Bookmarks are stored in this browser.')
    elif kind=='mistakes':abort(410,description='Permanent mistake history is not stored. Use Practice wrong answers on your current result.')
    if request.args.get('course_id'):q=q.join(Paper).filter(Paper.course_id==integer_argument('course_id'))
    if request.args.get('topic'):q=q.filter(Question.topic==request.args['topic'])
    return q

@exams.post('/attempts')
@require_visitor
def start():
    maintain_temporary_sessions()
    b=body();mode=b.get('mode','practice')
    if mode not in ('practice','exam'):abort(400,description='Choose practice or exam')
    if b.get('collection')=='mistakes' and b.get('attempt_id'):
        source=owned(b['attempt_id'])
        if source.status!='SUBMITTED' or mode!='practice':abort(409,description='Submit this attempt before practising its wrong answers')
        wrong=[i for i in source.items if i.outcome in ('INCORRECT','PARTIAL')]
        if not wrong:abort(409,description='No incorrect answers in this attempt')
        a=Attempt(user_id=None,guest_hash=g.guest_hash,paper_id=source.paper_id,mode='practice',title=('Wrong-answer practice · '+source.title)[:300],records_progress=False)
        return finish_new_attempt(a,[i.snapshot for i in wrong])
    kind=b.get('collection');p=None
    if kind:
        if kind not in ('bookmarks','topic') or mode!='practice':abort(400,description='Invalid practice collection')
        if kind=='bookmarks':
            ids=b.get('question_ids',[])
            if not isinstance(ids,list) or not 1<=len(ids)<=500 or any(type(i)!=int for i in ids):abort(400,description='Select 1–500 bookmarked questions.')
            q=Question.query.join(Paper).filter(Question.id.in_(ids),Question.status=='AVAILABLE',Paper.status!='ARCHIVED')
        else:q=collection_query(kind)
        if kind=='topic':
            if not b.get('topic') or not b.get('course_id'):abort(400,description='Course and topic required')
            q=q.join(Paper).filter(Paper.course_id==b['course_id'],Question.topic==b['topic'])
        title='Practice '+kind;deadline=None
    else:
        p=visible_papers(Paper.query).options(joinedload(Paper.course),joinedload(Paper.term),joinedload(Paper.exam_type)).filter_by(id=b.get('paper_id')).first_or_404();effective=p.canonical_paper_id or p.id;q=Question.query.filter_by(paper_id=effective,status='AVAILABLE').order_by(Question.id)
        title=f'{p.course.name} · {p.exam_type.name} · {p.term.name} · {p.name}'
        deadline=None
        if mode=='exam':
            duration=p.duration_seconds
            if not duration or 'duration_seconds' in b:
                try:duration=int(b.get('duration_seconds',0))
                except (TypeError,ValueError):abort(400,description='Choose a timed-practice duration')
                if not 60<=duration<=28800:abort(409,description='Source duration is unavailable. Choose a timed-practice duration of 1–480 minutes.')
                title+=' · timed practice (user-selected duration)'
            deadline=time.time()+duration
    if p:
        from .paper_content import snapshots as paper_snapshots
        snapshots=paper_snapshots(effective)[:500]
    else:
        questions=sorted(q.options(selectinload(Question.options),selectinload(Question.images)).limit(500).all(),key=lambda q:(q.paper_id,question_order(q.number),q.id))
        snapshots=[question_snapshot(q) for q in questions]
    if not snapshots:abort(409,description='Questions not imported yet.')
    # Unknown keys/marks remain ungraded; the result reports them separately.
    a=Attempt(user_id=None,guest_hash=g.guest_hash,paper_id=p.id if p else None,mode=mode,title=title[:300],deadline=deadline,records_progress=p is not None,expires_at=(deadline+RESULT_TTL_SECONDS) if deadline else time.time()+ACTIVE_TTL_SECONDS)
    return finish_new_attempt(a,snapshots)

@exams.get('/attempts')
@require_visitor
def history():
    expire_all(guest_hash=g.guest_hash)
    return jsonify(paginate(Attempt.query.filter_by(guest_hash=g.guest_hash,status='ACTIVE').order_by(Attempt.started_at.desc()),attempt_json))


@exams.delete('/attempts/<int:id>')
@require_visitor
def abandon(id):
    a=Attempt.query.filter_by(id=id,guest_hash=g.guest_hash).first()
    if a and a.status=='ACTIVE':
        db.session.delete(a);db.session.commit()
    return jsonify({'ok':True})

@exams.get('/attempts/<int:id>')
@require_visitor
def attempt(id):
    a=owned(id)
    return jsonify(bootstrap_json(a) if request.args.get('bootstrap')=='1' else attempt_json(a))

@exams.get('/attempts/<int:id>/status')
@require_visitor
def attempt_status(id):
    return jsonify(attempt_status_json(owned(id)))

@exams.get('/attempts/<int:id>/questions/<int:qid>')
@require_visitor
def attempt_question(id,qid):
    a=owned(id);i=AttemptAnswer.query.filter_by(attempt_id=a.id,question_id=qid).first_or_404()
    use_paper_image_delivery(a.paper_id)
    prepare_image_paths([i.snapshot],attempt_image_ttl(a))
    return jsonify(item_json(a,i,set()))

@exams.get('/attempts/<int:id>/questions')
@require_visitor
def attempt_questions(id):
    a=owned(id)
    use_paper_image_delivery(a.paper_id)
    bookmarks=set()
    items=sorted(a.items,key=lambda i:(i.snapshot.get('paper_id',0),question_order(i.snapshot['number']),i.position))
    prepare_image_paths([i.snapshot for i in items],attempt_image_ttl(a))
    return jsonify(items=[item_json(a,i,bookmarks) for i in items],status=a.status)

@exams.post('/attempts/<int:id>/answers')
@require_visitor
def answer(id):
    b=body()
    batched='items' in b
    raw=b.get('items') if batched else [b]
    if batched and (not isinstance(raw,list) or not 1<=len(raw)<=20):
        abort(400,description='Answer batch must contain 1–20 responses.')
    if not isinstance(raw,list):abort(400,description='Expected answer responses.')

    # Merge repeated question updates inside one browser flush (for example an
    # answer plus a review mark) so the database sees only the latest fields.
    merged={}
    for data in raw:
        if not isinstance(data,dict):abort(400,description='Each answer response must be an object.')
        qid=data.get('question_id')
        if not isinstance(qid,int) or isinstance(qid,bool):abort(400,description='question_id must be an integer.')
        if 'marked' in data and not isinstance(data['marked'],bool):abort(400,description='marked must be true or false.')
        merged[qid]={**merged.get(qid,{}),**data,'question_id':qid}
    updates=list(merged.values());qids=list(merged)

    # One owned-attempt/answer read handles the whole browser flush. A single
    # response remains fully backward compatible with the previous API.
    rows=(db.session.query(Attempt,AttemptAnswer)
          .join(AttemptAnswer,AttemptAnswer.attempt_id==Attempt.id)
          .filter(Attempt.id==id,Attempt.guest_hash==g.guest_hash,
                  AttemptAnswer.question_id.in_(qids)).all())
    if not rows or len(rows)!=len(qids):abort(404)
    a=rows[0][0];by_qid={i.question_id:i for _,i in rows}
    expire_attempt(a)
    if a.expires_at<=time.time():
        cleanup_sessions(guest_hash=g.guest_hash);abort(410,description='This temporary session has expired. Your latest paper score is retained; you can retake the paper.')
    if a.status!='ACTIVE':abort(409,description='Attempt already submitted or time expired')

    saved_at=time.time();results=[]
    for data in updates:
        i=by_qid[data['question_id']]
        if 'answer' in data:
            i.answer=normalize_answer(i.snapshot,data['answer']);i.response_touched=True
        if 'marked' in data:i.marked=data['marked']
        i.visited=True
        result={'question_id':i.question_id,'state':palette_state(i),'saved_at':saved_at}
        if a.mode=='practice' and i.answer is not None:
            result['feedback']={**grade(i.snapshot,i.answer),'answers':i.snapshot['answers'],'explanation':i.snapshot['explanation'],'answer_status':i.snapshot['answer_status']}
        results.append(result)

    # Serialize the whole flush against submission with one parent-version bump
    # and one commit rather than one transaction per response.
    a.version+=1
    db.session.commit()
    return jsonify(items=results) if batched else jsonify({k:v for k,v in results[0].items() if k!='question_id'})

@exams.post('/attempts/<int:id>/submit')
@require_visitor
def submit(id):return jsonify(attempt_json(submit_attempt(owned(id))))

@exams.get('/attempts/<int:id>/review')
@require_visitor
def review(id):
    a=owned(id)
    if a.status=='ACTIVE':abort(409,description='Submit the attempt before reviewing solutions')
    q=AttemptAnswer.query.filter_by(attempt_id=id).order_by(AttemptAnswer.position)
    return jsonify(paginate(q,lambda i:{'question':i.snapshot,'answer':i.answer,'outcome':i.outcome,'awarded':i.awarded,'manual_note':i.manual_note}))

@exams.route('/questions/<int:id>/bookmark',methods=['POST','DELETE'])
@require_visitor
def bookmark(id):
    abort(410,description='Bookmarks are stored in this browser.')

@exams.get('/bookmarks')
@exams.get('/mistakes')
@require_visitor
def collections():
    kind=request.path.rsplit('/',1)[1]
    return jsonify(paginate(collection_query(kind).order_by(Question.id),lambda q:question_with_image_urls(question_snapshot(q))))

@exams.get('/courses/<int:id>/topics')
def topics(id):
    rows=db.session.query(Question.topic,db.func.count(Question.id)).join(Paper).filter(Paper.course_id==id,Question.status=='AVAILABLE',Question.topic.isnot(None),Question.topic!='').group_by(Question.topic).all()
    return jsonify([{'topic':topic,'count':count} for topic,count in rows])

def progress_json(p):
    paper=db.session.get(Paper,p.paper_id)
    return {'paper_id':p.paper_id,'name':paper.name,'course':paper.course.name,'exam':paper.exam_type.name,'term':paper.term.name,'attempted':p.attempted,'last_score':p.last_score,'last_attempted_at':p.last_attempted_at}

@exams.get('/progress')
@require_visitor
def progress():
    return jsonify(items=[],total=0,page=1,limit=24)

@exams.get('/dashboard')
@require_visitor
def dashboard():
    expire_all(guest_hash=g.guest_hash)
    return jsonify(papers_attempted=0,bookmarks=0,active_sessions=Attempt.query.filter_by(guest_hash=g.guest_hash,status='ACTIVE').count())

@exams.get('/images/<int:id>')
@require_visitor
def question_image(id):
    row=db.session.query(QuestionImage,Question.status).join(Question,Question.id==QuestionImage.question_id).filter(QuestionImage.id==id).first()
    if row is None:abort(404)
    image,status=row
    if status!='AVAILABLE' and g.user.role!='ADMIN':
        prior=AttemptAnswer.query.join(Attempt).filter(Attempt.guest_hash==g.guest_hash,AttemptAnswer.question_id==image.question_id).first()
        if not prior:abort(404)
    # Normal requests keep the fast direct signed/CDN path. If the browser
    # reports that direct image as failed, QuestionContent retries with ?proxy=1;
    # never redirect that fallback back to the same broken signed URL.
    force_proxy=request.args.get('proxy')=='1'
    url=image_url(image.path,image.id)
    if not force_proxy and not url.startswith('/api/images/'):
        response=redirect(url,code=302);response.headers['Cache-Control']='private, max-age=300';return response
    try:
        response=send_asset(image.path,mimetype='image/png',conditional=True)
    except StorageError:
        # Older or partially uploaded papers may contain a DB image reference whose
        # object never reached R2. Rebuild that exact deterministic asset once from
        # the private source PDF, publish it, then serve it through this proxy.
        from .ingestion import repair_question_image_asset
        if not repair_question_image_asset(image):raise
        response=send_asset(image.path,mimetype='image/png',conditional=True)
    # Extracted question-image paths are immutable. Keep them in the user's
    # private browser cache for a year so revisiting/prefetching a formula never
    # triggers slow conditional 304 round-trips through Render.
    response.headers['Cache-Control']='private, max-age=31536000, immutable'
    response.vary.add('Cookie')
    return response

@exams.get('/papers/<int:id>/questions')
def paper_questions(id):
    from .paper_content import snapshots
    from .api import page_args
    p=visible_papers(Paper.query).filter_by(id=id).first_or_404();rows=snapshots(p.canonical_paper_id or p.id)
    page,size=page_args();selected=rows[(page-1)*size:page*size]
    use_paper_image_delivery(p.id)
    prepare_image_paths(selected)
    return jsonify(items=[question_with_image_urls(s) for s in selected],total=len(rows),page=page,limit=size)

@exams.get('/papers/<int:id>/source')
def source_pdf(id):
    p=visible_papers(Paper.query).filter_by(id=id).first_or_404();f=IngestionFile.query.filter(IngestionFile.paper_id==(p.canonical_paper_id or p.id),IngestionFile.path.isnot(None)).order_by(IngestionFile.id.desc()).first_or_404()
    # Source download is separate from the question API. Students can view original
    # source material; answer-bearing source pages never enter exam payloads/assets.
    return send_asset(f.path,mimetype='application/pdf',as_attachment=True,download_name='paper-'+str(p.id)+'.pdf')

@exams.post('/attempts/<int:id>/switch-mode')
@require_visitor
def switch_mode(id):
    source=owned(id);b=body();mode=b.get('mode')
    if source.status!='ACTIVE':abort(409,description='This attempt has ended')
    if mode not in ('practice','exam') or mode==source.mode:abort(400,description='Select the other mode')
    deadline=None
    if mode=='exam':
        try:duration=int(b.get('duration_seconds',5400))
        except (TypeError,ValueError):abort(400,description='Choose a duration in minutes')
        if not 60<=duration<=28800:abort(400,description='Duration must be 1–480 minutes')
        deadline=time.time()+duration
    # Change the existing session in place. No new snapshots or image URLs.
    source.mode=mode
    source.deadline=deadline
    source.expires_at=(deadline+RESULT_TTL_SECONDS) if deadline else time.time()+ACTIVE_TTL_SECONDS
    if mode=='exam' and not source.title.startswith('Assisted timed session · '):
        source.title=('Assisted timed session · '+source.title)[:300]
    feedback=[]
    if mode=='practice':
        feedback=[{'question_id':i.question_id,'feedback':{
            **grade(i.snapshot,i.answer),'answers':i.snapshot['answers'],
            'explanation':i.snapshot['explanation'],'answer_status':i.snapshot['answer_status']}}
            for i in source.items if i.answer is not None]
    payload={**attempt_status_json(source),'mode':source.mode,'title':source.title,'feedback':feedback}
    db.session.commit()
    return jsonify(payload),200



@exams.post('/questions/<int:id>/report-format')
@limiter.limit('60 per hour')
@require_visitor
def report_format(id):
    from sqlalchemy.exc import IntegrityError
    q=Question.query.join(Paper,Paper.id==Question.paper_id).filter(Question.id==id,Question.status=='AVAILABLE',Paper.status!='ARCHIVED').first_or_404()
    payload=body();issue=payload.get('issue');description=payload.get('description','')
    if issue not in ('TEXT','FORMULA','IMAGE','OPTIONS','OTHER'):abort(400,description='Choose a valid formatting issue.')
    if not isinstance(description,str) or len(description)>1000:abort(400,description='Description must be at most 1000 characters.')
    existing=ContentReport.query.filter_by(question_id=q.id,guest_hash=g.guest_hash).first()
    if existing:return jsonify(id=existing.id,duplicate=True,status=existing.status)
    if ContentReport.query.filter(ContentReport.guest_hash==g.guest_hash,ContentReport.created_at>time.time()-3600).count()>=20:abort(429,description='Too many reports. Please try again later.')
    report=ContentReport(question_id=q.id,guest_hash=g.guest_hash,issue=issue,description=description.strip())
    db.session.add(report)
    try:db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing=ContentReport.query.filter_by(question_id=q.id,guest_hash=g.guest_hash).first()
        if not existing:raise
        return jsonify(id=existing.id,duplicate=True,status=existing.status)
    return jsonify(id=report.id,duplicate=False,status=report.status),201
