import secrets,re
from functools import wraps
from flask import Blueprint,jsonify,request,session,g,abort
from werkzeug.security import generate_password_hash,check_password_hash
from sqlalchemy import or_,func
from .models import *
from . import limiter
api=Blueprint('api',__name__,url_prefix='/api')

def integer_argument(name):
    raw=request.args.get(name)
    try:value=int(raw)
    except (TypeError,ValueError):abort(400,description=name+' must be an integer')
    if not 0<=value<=2147483647:abort(400,description=name+' is out of range')
    return value

def require_user(admin=False):
    def deco(fn):
        @wraps(fn)
        def inner(*a,**kw):
            g.user=db.session.get(User,session.get('uid')) if session.get('uid') else None
            if not g.user or not g.user.active:abort(401,description='Please sign in.')
            if admin and g.user.role!='ADMIN':abort(403,description='Administrator access required.')
            return fn(*a,**kw)
        return inner
    return deco

def body():
    value=request.get_json(silent=True)
    if not isinstance(value,dict):abort(400,description='Expected a JSON object')
    return value

def user_json(u):return {'id':u.id,'name':u.name,'email':u.email,'role':u.role}
def page_args():
    try:return max(1,int(request.args.get('page',1))),min(100,max(1,int(request.args.get('limit',24))))
    except ValueError:abort(400,description='Invalid pagination')
def paginate(query,mapper):
    page,size=page_args();total=query.count()
    return {'items':[mapper(x) for x in query.limit(size).offset((page-1)*size).all()],'total':total,'page':page,'limit':size}

def paper_json(p):
    effective=db.session.get(Paper,p.canonical_paper_id) if p.canonical_paper_id else p
    questions=Question.query.filter_by(paper_id=effective.id,status='AVAILABLE').all();count=len(questions)
    user=db.session.get(User,session.get('uid')) if session.get('uid') else None
    progress=db.session.get(PaperProgress,(user.id,p.id)) if user and user.active else None
    return {'progress':({'attempted':progress.attempted,'last_score':progress.last_score,'last_attempted_at':progress.last_attempted_at} if progress else None),'id':p.id,'name':p.name,'course_id':p.course_id,'course':p.course.name,'code':p.course.code,'exam':p.exam_type.name,'exam_type_id':p.exam_type_id,'term':p.term.name,'term_id':p.term_id,'year':p.term.year,'session':p.session,'source_url':p.source_url,'status':p.status,'warnings':p.warnings,'question_count':count,'practice_available':count>0,'duration_seconds':effective.duration_seconds,'source_metadata':effective.source_metadata,'canonical_paper_id':p.canonical_paper_id,'total_marks':sum(q.marks for q in questions) if questions and all(q.marks is not None for q in questions) else None,'unknown_keys':sum(q.answer_status!='ANSWER_AVAILABLE' for q in questions),'download_url':'/api/papers/'+str(p.id)+'/source' if IngestionFile.query.filter(IngestionFile.paper_id==effective.id,IngestionFile.path.isnot(None)).first() else None}

def course_json(c):
    groups=db.session.query(ExamType.name,func.count(Paper.id)).join(Paper,Paper.exam_type_id==ExamType.id).filter(Paper.course_id==c.id).group_by(ExamType.name).all()
    years=[r[0] for r in db.session.query(Term.year).join(Paper,Paper.term_id==Term.id).filter(Paper.course_id==c.id).distinct().order_by(Term.year.desc())]
    return {'id':c.id,'name':c.name,'code':c.code,'level':c.level,'course_type':c.course_type,'exams':dict(groups),'years':years,'paper_count':sum(n for _,n in groups),'question_count':db.session.query(Question).join(Paper).filter(Paper.course_id==c.id,Question.status=='AVAILABLE').count()}

@api.get('/session')
def current_session():
    session.setdefault('csrf',secrets.token_urlsafe(32))
    u=db.session.get(User,session.get('uid')) if session.get('uid') else None
    return jsonify(csrf=session['csrf'],user=user_json(u) if u and u.active else None)

@api.post('/auth/register')
@limiter.limit('10 per hour')
def register():
    b=body();email=str(b.get('email','')).strip().lower();password=b.get('password','');name=str(b.get('name','')).strip()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254:abort(400,description='Enter a valid email address.')
    if not isinstance(password,str) or not 12<=len(password)<=128:abort(400,description='Use a password of 12–128 characters.')
    if not 1<=len(name)<=100:abort(400,description='Enter a name of 1–100 characters.')
    u=User(email=email,name=name,password_hash=generate_password_hash(password));db.session.add(u);db.session.commit()
    session.clear();session.update(uid=u.id,csrf=secrets.token_urlsafe(32));session.permanent=True
    return jsonify(user=user_json(u),csrf=session['csrf']),201

@api.post('/auth/login')
@limiter.limit('10 per minute')
def login():
    b=body();u=User.query.filter_by(email=str(b.get('email','')).lower().strip()).first();password=b.get('password','')
    if not isinstance(password,str) or len(password)>128 or not u or not u.active or not check_password_hash(u.password_hash,password):abort(401,description='Invalid email or password.')
    session.clear();session.update(uid=u.id,csrf=secrets.token_urlsafe(32));session.permanent=True
    return jsonify(user=user_json(u),csrf=session['csrf'])

@api.post('/auth/logout')
def logout():
    session.clear();session['csrf']=secrets.token_urlsafe(32)
    return jsonify(csrf=session['csrf'])

@api.get('/stats')
def stats():return jsonify(courses=Course.query.count(),papers=Paper.query.count(),questions=Question.query.filter_by(status='AVAILABLE').count())

@api.get('/courses')
def courses():
    q=Course.query;term=request.args.get('q','')[:150]
    if term:q=q.filter(or_(Course.name.ilike('%'+term+'%'),Course.code.ilike('%'+term+'%')))
    if request.args.get('level'):q=q.filter_by(level=request.args['level'])
    if request.args.get('sort')=='papers':q=q.outerjoin(Paper).group_by(Course.id).order_by(func.count(Paper.id).desc(),Course.name)
    else:q=q.order_by(Course.name)
    return jsonify(paginate(q,course_json))

@api.get('/courses/<int:id>')
def course(id):return jsonify(course_json(db.get_or_404(Course,id)))

@api.get('/courses/<int:id>/exams')
def course_exams(id):return jsonify(course_json(db.get_or_404(Course,id))['exams'])

@api.get('/papers')
def papers():
    q=Paper.query.join(Course).join(Term).join(ExamType)
    for key,col in [('course_id',Paper.course_id),('exam_type_id',Paper.exam_type_id),('year',Term.year),('term_id',Term.id)]:
        if request.args.get(key):q=q.filter(col==integer_argument(key))
    if request.args.get('exam'):q=q.filter(ExamType.name==request.args['exam'])
    if request.args.get('available')=='true':
        ready=db.session.query(Question.paper_id).filter(Question.status=='AVAILABLE')
        q=q.filter(or_(Paper.id.in_(ready),Paper.canonical_paper_id.in_(ready)))
    if request.args.get('q'):
        for word in request.args['q'][:150].split():
            like='%'+word+'%';q=q.filter(or_(Paper.name.ilike(like),Course.name.ilike(like),Term.name.ilike(like),ExamType.name.ilike(like)))
    return jsonify(paginate(q.order_by(Term.year.desc(),Term.month.desc(),Paper.id),paper_json))

@api.get('/papers/<int:id>')
def paper(id):return jsonify(paper_json(db.get_or_404(Paper,id)))

@api.get('/metadata')
def metadata():return jsonify(terms=[{'id':x.id,'name':x.name,'year':x.year} for x in Term.query.order_by(Term.year.desc(),Term.month.desc())],exams=[{'id':x.id,'name':x.name} for x in ExamType.query.all()],levels=[r[0] for r in db.session.query(Course.level).distinct()])

@api.get('/search')
def search():
    text=request.args.get('q','').strip()[:150]
    if len(text)<2:return jsonify(courses=[],papers=[],questions=[])
    like='%'+text+'%'
    return jsonify(courses=[{'id':c.id,'name':c.name} for c in Course.query.filter(or_(Course.name.ilike(like),Course.code.ilike(like))).limit(20)],papers=[paper_json(p) for p in Paper.query.filter(Paper.name.ilike(like)).limit(20)],questions=[{'id':q.id,'text':q.text[:300],'paper_id':q.paper_id,'topic':q.topic} for q in Question.query.filter(Question.status=='AVAILABLE',Question.text.ilike(like)).limit(20)])

@api.get('/demo-papers')
def demo_papers():
    import json
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'demo-papers.json'
    ids=json.loads(path.read_text()).get('paper_ids',[]) if path.exists() else []
    return jsonify(items=[paper_json(p) for id in ids if (p:=db.session.get(Paper,id))])
