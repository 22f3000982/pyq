import secrets,re,hashlib
from types import SimpleNamespace
from functools import wraps
from flask import Blueprint,jsonify,request,session,g,abort
from werkzeug.security import generate_password_hash,check_password_hash
from sqlalchemy import or_,and_,func,case
from sqlalchemy.orm import joinedload
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

def require_visitor(fn):
    """Signed session cookie identifies a browser; no student account is created."""
    @wraps(fn)
    def inner(*args,**kwargs):
        session.setdefault('visitor',secrets.token_urlsafe(32))
        session.permanent=True
        g.guest_hash=hashlib.sha256(session['visitor'].encode()).hexdigest()
        admin=db.session.get(User,session.get('uid')) if session.get('uid') else None
        g.user=admin if admin and admin.active and admin.role=='ADMIN' else SimpleNamespace(id=None,role='GUEST',name='Guest',active=True)
        return fn(*args,**kwargs)
    return inner

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

def _paper_content_rows(papers):
    """Batch catalog counts and user progress; never materialize question bodies."""
    if not papers:return []
    ids=[p.id for p in papers];effective_ids={p.canonical_paper_id or p.id for p in papers}
    effective={p.id:p for p in papers}
    missing=effective_ids-set(effective)
    if missing:effective.update({p.id:p for p in Paper.query.filter(Paper.id.in_(missing))})
    totals={r[0]:r[1:] for r in db.session.query(Question.paper_id,func.count(Question.id),func.count(Question.marks),func.sum(Question.marks),func.sum(case((Question.answer_status=='ANSWER_AVAILABLE',0),else_=1))).filter(Question.paper_id.in_(effective_ids),Question.status=='AVAILABLE').group_by(Question.paper_id)}
    downloads={r[0] for r in db.session.query(IngestionFile.paper_id).filter(IngestionFile.paper_id.in_(effective_ids),IngestionFile.path.isnot(None)).distinct()}
    out=[]
    for p in papers:
        e=effective[p.canonical_paper_id or p.id];count,marked,total,unknown=totals.get(e.id,(0,0,None,0))
        out.append({'progress':None,'id':p.id,'name':p.name,'course_id':p.course_id,'course':p.course.name,'code':p.course.code,'exam':p.exam_type.name,'exam_type_id':p.exam_type_id,'term':p.term.name,'term_id':p.term_id,'year':p.term.year,'session':p.session,'source_url':p.source_url,'status':p.status,'warnings':p.warnings,'question_count':count,'practice_available':count>0,'duration_seconds':e.duration_seconds,'source_metadata':e.source_metadata,'canonical_paper_id':p.canonical_paper_id,'total_marks':total if count and marked==count else None,'unknown_keys':unknown,'download_url':'/api/papers/'+str(p.id)+'/source' if e.id in downloads else None})
    return out

def paper_rows(papers):
    if not papers:return []
    import hashlib
    from .content_cache import cached
    ids=[p.id for p in papers]
    key='paper-metadata:'+hashlib.sha256(','.join(map(str,ids)).encode()).hexdigest()
    rows=cached(key,lambda:_paper_content_rows(papers))
    return [{**row,'progress':None} for row in rows]

PAPER_LOAD=(joinedload(Paper.course),joinedload(Paper.term),joinedload(Paper.exam_type))
def visible_papers(query=None):
    q=query if query is not None else Paper.query
    return q.filter(Paper.status!='ARCHIVED')
def paper_json(p):return paper_rows([p])[0]

def course_rows(courses):
    if not courses:return []
    ids=[c.id for c in courses];groups={id:{} for id in ids};years={id:[] for id in ids}
    for cid,name,count in db.session.query(Paper.course_id,ExamType.name,func.count(Paper.id)).join(ExamType,Paper.exam_type_id==ExamType.id).filter(Paper.course_id.in_(ids),Paper.status!='ARCHIVED').group_by(Paper.course_id,ExamType.name):groups[cid][name]=count
    for cid,year in db.session.query(Paper.course_id,Term.year).join(Term,Paper.term_id==Term.id).filter(Paper.course_id.in_(ids),Paper.status!='ARCHIVED').distinct().order_by(Term.year.desc()):years[cid].append(year)
    counts=dict(db.session.query(Paper.course_id,func.count(Question.id)).join(Question,Question.paper_id==Paper.id).filter(Paper.course_id.in_(ids),Paper.status!='ARCHIVED',Question.status=='AVAILABLE').group_by(Paper.course_id).all())
    return [{'id':c.id,'name':c.name,'code':c.code,'level':c.level,'course_type':c.course_type,'exams':groups[c.id],'years':years[c.id],'paper_count':sum(groups[c.id].values()),'question_count':counts.get(c.id,0)} for c in courses]

def course_json(c):return course_rows([c])[0]
def paginate_rows(query,mapper):
    page,size=page_args();total=query.count()
    return {'items':mapper(query.limit(size).offset((page-1)*size).all()),'total':total,'page':page,'limit':size}

@api.get('/session')
def current_session():
    session.setdefault('csrf',secrets.token_urlsafe(32))
    session.setdefault('visitor',secrets.token_urlsafe(32));session.permanent=True
    u=db.session.get(User,session.get('uid')) if session.get('uid') else None
    return jsonify(csrf=session['csrf'],user=user_json(u) if u and u.active and u.role=='ADMIN' else None)

@api.post('/auth/register')
@limiter.limit('10 per hour')
def register():
    abort(410,description='Student accounts are no longer required. Open a paper to start practising.')

@api.post('/auth/login')
@limiter.limit('10 per minute')
def login():
    b=body();u=User.query.filter_by(email=str(b.get('email','')).lower().strip()).first();password=b.get('password','')
    if not isinstance(password,str) or len(password)>128 or not u or not u.active or u.role!='ADMIN' or not check_password_hash(u.password_hash,password):abort(401,description='Invalid email or password.')
    visitor=session.get('visitor') or secrets.token_urlsafe(32)
    session.clear();session.update(uid=u.id,visitor=visitor,csrf=secrets.token_urlsafe(32));session.permanent=True
    return jsonify(user=user_json(u),csrf=session['csrf'])

@api.post('/auth/logout')
def logout():
    visitor=session.get('visitor') or secrets.token_urlsafe(32)
    session.clear();session.update(visitor=visitor,csrf=secrets.token_urlsafe(32));session.permanent=True
    return jsonify(csrf=session['csrf'])

@api.get('/stats')
def stats():
    from .content_cache import cached
    def load():
        ready=db.session.query(Question.paper_id).filter(Question.status=='AVAILABLE').distinct().subquery()
        visible_effective=db.session.query(func.coalesce(Paper.canonical_paper_id,Paper.id).label('paper_id')).filter(Paper.status!='ARCHIVED').distinct().subquery()
        available=(db.session.query(ExamType.name,func.count(Paper.id))
            .join(Paper,Paper.exam_type_id==ExamType.id)
            .filter(Paper.status!='ARCHIVED',or_(Paper.id.in_(ready),Paper.canonical_paper_id.in_(ready)))
            .group_by(ExamType.name).all())
        return dict(courses=Course.query.count(),papers=Paper.query.filter(Paper.status!='ARCHIVED').count(),
                    questions=Question.query.filter(Question.status=='AVAILABLE',Question.paper_id.in_(visible_effective)).count(),
                    exam_papers={name:count for name,count in available})
    return jsonify(cached('public-stats',load))

@api.get('/courses')
def courses():
    q=Course.query;term=request.args.get('q','')[:150]
    if term:q=q.filter(or_(Course.name.ilike('%'+term+'%'),Course.code.ilike('%'+term+'%')))
    if request.args.get('level'):q=q.filter_by(level=request.args['level'])
    if request.args.get('sort')=='papers':q=q.outerjoin(Paper,and_(Paper.course_id==Course.id,Paper.status!='ARCHIVED')).group_by(Course.id).order_by(func.count(Paper.id).desc(),Course.name)
    else:q=q.order_by(Course.name)
    return jsonify(paginate_rows(q,course_rows))

@api.get('/courses/<int:id>')
def course(id):return jsonify(course_json(db.get_or_404(Course,id)))

@api.get('/courses/<int:id>/exams')
def course_exams(id):return jsonify(course_json(db.get_or_404(Course,id))['exams'])

def cached_public_response(name, loader):
    from .content_cache import cached
    import json
    # Include all query arguments: filters and pagination must never collide.
    key=name+':'+hashlib.sha256(json.dumps(sorted(request.args.items(multi=True))).encode()).hexdigest()
    return jsonify(cached(key,loader))

@api.get('/papers')
def papers():
    return cached_public_response('paper-list', _paper_list)

def _paper_list():
    q=visible_papers(Paper.query).join(Course).join(Term).join(ExamType)
    for key,col in [('course_id',Paper.course_id),('exam_type_id',Paper.exam_type_id),('year',Term.year),('term_id',Term.id)]:
        if request.args.get(key):q=q.filter(col==integer_argument(key))
    if request.args.get('exam'):q=q.filter(ExamType.name==request.args['exam'])
    if request.args.get('available')=='true':
        ready=db.session.query(Question.paper_id).filter(Question.status=='AVAILABLE')
        q=q.filter(or_(Paper.id.in_(ready),Paper.canonical_paper_id.in_(ready)))
    if request.args.get('q'):
        for word in request.args['q'][:150].split():
            like='%'+word+'%';q=q.filter(or_(Paper.name.ilike(like),Course.name.ilike(like),Term.name.ilike(like),ExamType.name.ilike(like)))
    return paginate_rows(q.options(*PAPER_LOAD).order_by(Term.year.desc(),Term.month.desc(),Paper.id),paper_rows)

@api.get('/papers/<int:id>')
def paper(id):
    return cached_public_response('paper-detail:'+str(id),lambda:paper_json(visible_papers(Paper.query).options(*PAPER_LOAD).filter_by(id=id).first_or_404()))

@api.get('/metadata')
def metadata():
    return cached_public_response('metadata', _metadata)

def _metadata():return dict(terms=[{'id':x.id,'name':x.name,'year':x.year} for x in Term.query.order_by(Term.year.desc(),Term.month.desc())],exams=[{'id':x.id,'name':x.name} for x in ExamType.query.all()],levels=[r[0] for r in db.session.query(Course.level).distinct()])

@api.get('/search')
def search():
    text=request.args.get('q','').strip()[:150]
    if len(text)<2:return jsonify(courses=[],papers=[],questions=[])
    like='%'+text+'%'
    visible_effective=db.session.query(func.coalesce(Paper.canonical_paper_id,Paper.id).label('paper_id')).filter(Paper.status!='ARCHIVED').distinct().subquery()
    return jsonify(courses=[{'id':c.id,'name':c.name} for c in Course.query.filter(or_(Course.name.ilike(like),Course.code.ilike(like))).limit(20)],papers=paper_rows(visible_papers(Paper.query).options(*PAPER_LOAD).filter(Paper.name.ilike(like)).limit(20).all()),questions=[{'id':q.id,'text':q.text[:300],'paper_id':q.paper_id,'topic':q.topic} for q in Question.query.filter(Question.status=='AVAILABLE',Question.paper_id.in_(visible_effective),Question.text.ilike(like)).limit(20)])

@api.get('/demo-papers')
def demo_papers():
    import json
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'demo-papers.json'
    ids=json.loads(path.read_text()).get('paper_ids',[]) if path.exists() else []
    records={p.id:p for p in visible_papers(Paper.query).options(*PAPER_LOAD).filter(Paper.id.in_(ids))}
    featured=[records[id] for id in ids if id in records]
    ready=db.session.query(Question.paper_id).filter(Question.status=='AVAILABLE')
    recent=visible_papers(Paper.query).join(Course).join(Term).join(ExamType).filter(or_(Paper.id.in_(ready),Paper.canonical_paper_id.in_(ready))).options(*PAPER_LOAD).order_by(Paper.id.desc()).limit(6).all()
    seen={paper.id for paper in featured}
    featured.extend(paper for paper in recent if paper.id not in seen)
    return jsonify(items=paper_rows(featured))

@api.get('/recent-papers')
def recent_papers():
    ready=db.session.query(Question.paper_id).filter(Question.status=='AVAILABLE')
    q=visible_papers(Paper.query).join(Course).join(Term).join(ExamType).filter(or_(Paper.id.in_(ready),Paper.canonical_paper_id.in_(ready)))
    return jsonify(items=paper_rows(q.options(*PAPER_LOAD).order_by(Paper.id.desc()).limit(6).all()))

@api.get('/catalog')
def catalog_options():
    # Complete lightweight dropdown catalog, with no pagination truncation.
    from .content_cache import cached
    return jsonify(cached('catalog',lambda:dict(courses=course_rows(Course.query.order_by(Course.name).all()),meta=metadata().get_json())))


@api.get('/home')
def home():
    # Public content only: session/CSRF and student state stay separate.
    return cached_public_response('home',lambda:dict(
        stats=stats().get_json(),**catalog_options().get_json()))
