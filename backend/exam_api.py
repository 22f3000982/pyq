from .storage import send_asset,image_url,StorageError
import time
from flask import Blueprint,jsonify,request,g,abort,current_app,send_from_directory,redirect
from sqlalchemy import or_
from sqlalchemy.orm import selectinload,joinedload
from .models import *
from .api import integer_argument,require_user,body,paginate
from .engine import *
exams=Blueprint('exams',__name__,url_prefix='/api')

def owned(id):
    a=db.get_or_404(Attempt,id)
    if a.user_id!=g.user.id:abort(404)
    expire_attempt(a)
    if a.expires_at<=time.time():
        cleanup_sessions();abort(410,description='This temporary session has expired. Your latest paper score is retained; you can retake the paper.')
    return a

def attempt_json(a):return {'id':a.id,'paper_id':a.paper_id,'title':a.title,'mode':a.mode,'status':a.status,'started_at':a.started_at,'deadline':a.deadline,'submitted_at':a.submitted_at,'server_time':time.time(),'result':a.result,'expires_at':a.expires_at,'records_progress':a.records_progress,'palette':[{'question_id':i.question_id,'number':i.snapshot['number'],'state':palette_state(i),'visited':i.visited,'marked':i.marked} for i in sorted(a.items,key=lambda i:(i.snapshot.get("paper_id",0),question_order(i.snapshot["number"]),i.position))]}

def question_with_image_urls(snapshot):
    result=public_question(snapshot)
    paths=getattr(g,'image_paths',{})
    result['images']=[{**image,'url':image_url(paths.get(image['id']),image['id']) if paths.get(image['id']) else '/api/images/'+str(image['id'])} for image in result.get('images',[]) if image.get('id') is not None]
    return result

def prepare_image_paths(snapshots):
    if current_app.config.get('IMAGE_DELIVERY','proxy')=='proxy':return
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
    prepare_image_paths([i.snapshot for i in items])
    bookmarks={qid for qid, in db.session.query(Bookmark.question_id).filter(Bookmark.user_id==g.user.id,Bookmark.question_id.in_([i.question_id for i in items]))}
    return {**attempt_json(a),'items':[item_json(a,i,bookmarks) for i in items]}

def start_response(a):
    # The legacy response remains supported; frontend opts into the combined payload.
    return jsonify(bootstrap_json(a) if request.args.get('bootstrap')=='1' else attempt_json(a)),201

def item_json(a,i,bookmarks):
    result={'question':question_with_image_urls(i.snapshot),'answer':i.answer,'marked':i.marked,'visited':i.visited,'status':a.status,'bookmarked':i.question_id in bookmarks}
    if a.status!='ACTIVE' or (a.mode=='practice' and i.answer is not None):
        result['feedback']={**grade(i.snapshot,i.answer),'answers':i.snapshot['answers'],'explanation':i.snapshot['explanation'],'answer_status':i.snapshot['answer_status']}
    return result

def collection_query(kind):
    q=Question.query.filter(Question.status=='AVAILABLE')
    if kind=='bookmarks':q=q.join(Bookmark).filter(Bookmark.user_id==g.user.id)
    elif kind=='mistakes':abort(410,description='Permanent mistake history is not stored. Use Practice wrong answers on your current result.')
    if request.args.get('course_id'):q=q.join(Paper).filter(Paper.course_id==integer_argument('course_id'))
    if request.args.get('topic'):q=q.filter(Question.topic==request.args['topic'])
    return q

@exams.post('/attempts')
@require_user()
def start():
    expire_all(user_id=g.user.id)
    b=body();mode=b.get('mode','practice')
    if mode not in ('practice','exam'):abort(400,description='Choose practice or exam')
    if b.get('collection')=='mistakes' and b.get('attempt_id'):
        source=owned(b['attempt_id'])
        if source.status!='SUBMITTED' or mode!='practice':abort(409,description='Submit this attempt before practising its wrong answers')
        wrong=[i for i in source.items if i.outcome=='INCORRECT']
        if not wrong:abort(409,description='No incorrect answers in this attempt')
        a=Attempt(user_id=g.user.id,paper_id=source.paper_id,mode='practice',title=('Wrong-answer practice · '+source.title)[:300],records_progress=False)
        db.session.add(a);db.session.flush()
        for n,i in enumerate(wrong):db.session.add(AttemptAnswer(attempt_id=a.id,question_id=i.question_id,position=n,snapshot=i.snapshot))
        db.session.commit();return start_response(a)
    kind=b.get('collection');p=None
    if kind:
        if kind not in ('bookmarks','topic') or mode!='practice':abort(400,description='Invalid practice collection')
        q=collection_query(kind)
        if kind=='topic':
            if not b.get('topic') or not b.get('course_id'):abort(400,description='Course and topic required')
            q=q.join(Paper).filter(Paper.course_id==b['course_id'],Question.topic==b['topic'])
        title='Practice '+kind;deadline=None
    else:
        p=Paper.query.options(joinedload(Paper.course),joinedload(Paper.term),joinedload(Paper.exam_type)).filter_by(id=b.get('paper_id')).first_or_404();effective=p.canonical_paper_id or p.id;q=Question.query.filter_by(paper_id=effective,status='AVAILABLE').order_by(Question.id)
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
    a=Attempt(user_id=g.user.id,paper_id=p.id if p else None,mode=mode,title=title[:300],deadline=deadline,records_progress=p is not None,expires_at=(deadline+RESULT_TTL_SECONDS) if deadline else time.time()+ACTIVE_TTL_SECONDS)
    db.session.add(a);db.session.flush()
    for n,s in enumerate(snapshots):db.session.add(AttemptAnswer(attempt_id=a.id,question_id=s['id'],position=n,snapshot=s))
    db.session.commit();return start_response(a)

@exams.get('/attempts')
@require_user()
def history():
    expire_all(user_id=g.user.id)
    return jsonify(paginate(Attempt.query.filter_by(user_id=g.user.id,status='ACTIVE').order_by(Attempt.started_at.desc()),attempt_json))

@exams.get('/attempts/<int:id>')
@require_user()
def attempt(id):
    a=owned(id)
    return jsonify(bootstrap_json(a) if request.args.get('bootstrap')=='1' else attempt_json(a))

@exams.get('/attempts/<int:id>/questions/<int:qid>')
@require_user()
def attempt_question(id,qid):
    a=owned(id);i=AttemptAnswer.query.filter_by(attempt_id=a.id,question_id=qid).first_or_404()
    return jsonify(item_json(a,i,{qid} if db.session.get(Bookmark,(g.user.id,qid)) else set()))

@exams.get('/attempts/<int:id>/questions')
@require_user()
def attempt_questions(id):
    a=owned(id)
    bookmarks={qid for qid, in db.session.query(Bookmark.question_id).filter_by(user_id=g.user.id)}
    items=sorted(a.items,key=lambda i:(i.snapshot.get('paper_id',0),question_order(i.snapshot['number']),i.position))
    prepare_image_paths([i.snapshot for i in items])
    return jsonify(items=[item_json(a,i,bookmarks) for i in items],status=a.status)

@exams.post('/attempts/<int:id>/answers')
@require_user()
def answer(id):
    a=owned(id)
    if a.status!='ACTIVE':abort(409,description='Attempt already submitted or time expired')
    b=body();i=AttemptAnswer.query.filter_by(attempt_id=a.id,question_id=b.get('question_id')).first_or_404()
    if 'answer' in b:
        i.answer=normalize_answer(i.snapshot,b['answer']);i.response_touched=True
    if 'marked' in b:
        if not isinstance(b['marked'],bool):abort(400)
        i.marked=b['marked']
    i.visited=True
    # All answer writes update parent version, serializing against submission.
    a.version+=1
    result={'state':palette_state(i),'saved_at':time.time()}
    if a.mode=='practice' and i.answer is not None:result['feedback']={**grade(i.snapshot,i.answer),'answers':i.snapshot['answers'],'explanation':i.snapshot['explanation'],'answer_status':i.snapshot['answer_status']}
    db.session.commit()
    return jsonify(result)

@exams.post('/attempts/<int:id>/submit')
@require_user()
def submit(id):return jsonify(attempt_json(submit_attempt(owned(id))))

@exams.get('/attempts/<int:id>/review')
@require_user()
def review(id):
    a=owned(id)
    if a.status=='ACTIVE':abort(409,description='Submit the attempt before reviewing solutions')
    q=AttemptAnswer.query.filter_by(attempt_id=id).order_by(AttemptAnswer.position)
    return jsonify(paginate(q,lambda i:{'question':i.snapshot,'answer':i.answer,'outcome':i.outcome,'awarded':i.awarded,'manual_note':i.manual_note}))

@exams.route('/questions/<int:id>/bookmark',methods=['POST','DELETE'])
@require_user()
def bookmark(id):
    q=db.get_or_404(Question,id)
    if q.status!='AVAILABLE':abort(404)
    old=db.session.get(Bookmark,(g.user.id,id))
    if request.method=='POST' and not old:db.session.add(Bookmark(user_id=g.user.id,question_id=id))
    if request.method=='DELETE' and old:db.session.delete(old)
    db.session.commit();return jsonify(bookmarked=request.method=='POST')

@exams.get('/bookmarks')
@exams.get('/mistakes')
@require_user()
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
@require_user()
def progress():
    return jsonify(paginate(PaperProgress.query.filter_by(user_id=g.user.id).order_by(PaperProgress.last_attempted_at.desc(),PaperProgress.paper_id),progress_json))

@exams.get('/dashboard')
@require_user()
def dashboard():
    expire_all(user_id=g.user.id)
    return jsonify(papers_attempted=PaperProgress.query.filter_by(user_id=g.user.id).count(),bookmarks=Bookmark.query.filter_by(user_id=g.user.id).count(),active_sessions=Attempt.query.filter_by(user_id=g.user.id,status='ACTIVE').count())

@exams.get('/images/<int:id>')
@require_user()
def question_image(id):
    row=db.session.query(QuestionImage,Question.status).join(Question,Question.id==QuestionImage.question_id).filter(QuestionImage.id==id).first()
    if row is None:abort(404)
    image,status=row
    if status!='AVAILABLE' and g.user.role!='ADMIN':
        prior=AttemptAnswer.query.join(Attempt).filter(Attempt.user_id==g.user.id,AttemptAnswer.question_id==image.question_id).first()
        if not prior:abort(404)
    url=image_url(image.path,image.id)
    if not url.startswith('/api/images/'):
        response=redirect(url,code=302);response.headers['Cache-Control']='private, no-store';return response
    response=send_asset(image.path,mimetype='image/png',conditional=True)
    response.headers['Cache-Control']='private, max-age=3600'
    response.vary.add('Cookie')
    return response

@exams.get('/papers/<int:id>/questions')
def paper_questions(id):
    from .paper_content import snapshots
    from .api import page_args
    p=db.get_or_404(Paper,id);rows=snapshots(p.canonical_paper_id or p.id)
    page,size=page_args();selected=rows[(page-1)*size:page*size]
    prepare_image_paths(selected)
    return jsonify(items=[question_with_image_urls(s) for s in selected],total=len(rows),page=page,limit=size)

@exams.get('/papers/<int:id>/source')
def source_pdf(id):
    p=db.get_or_404(Paper,id);f=IngestionFile.query.filter(IngestionFile.paper_id==(p.canonical_paper_id or p.id),IngestionFile.path.isnot(None)).order_by(IngestionFile.id.desc()).first_or_404()
    # Source download is separate from the question API. Students can view original
    # source material; answer-bearing source pages never enter exam payloads/assets.
    return send_asset(f.path,mimetype='application/pdf',as_attachment=True,download_name='paper-'+str(p.id)+'.pdf')

@exams.post('/attempts/<int:id>/switch-mode')
@require_user()
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
    # Freeze the old timed score before any answers are revealed. A new continuation
    # uses the same snapshots/responses; a practice-to-exam continuation is assisted.
    submit_attempt(source,record_progress=False)
    title=('Assisted timed continuation · ' if mode=='exam' else 'Practice continuation · ')+source.title
    a=Attempt(user_id=g.user.id,paper_id=source.paper_id,mode=mode,title=title[:300],deadline=deadline,records_progress=source.records_progress,expires_at=(deadline+RESULT_TTL_SECONDS) if deadline else time.time()+ACTIVE_TTL_SECONDS)
    db.session.add(a);db.session.flush()
    for i in source.items:
        db.session.add(AttemptAnswer(attempt_id=a.id,question_id=i.question_id,position=i.position,snapshot=i.snapshot,answer=i.answer,visited=i.visited,marked=i.marked,response_touched=i.response_touched))
    db.session.commit();return start_response(a)
