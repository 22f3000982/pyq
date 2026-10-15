"""On-demand administrator audits. Heuristics flag candidates, never delete content."""
import hashlib,json,re,time
from flask import Blueprint,request,jsonify,abort,current_app
from sqlalchemy.orm import selectinload
from .models import db,Question,Paper,AISolution,ContentQualityReview,Course,CourseGuide,StudyPaperSettings
from .api import require_user,body,integer_argument
from .engine import question_snapshot,grade
from .ai_solutions import version
from .public_content import TOKEN,paper_title
quality=Blueprint('quality',__name__,url_prefix='/api/admin/content-quality')
CHECKS=('source','calculation','options','formatting')
FIELDS=('introduction','topics','prerequisites','mistakes','practice')

def fingerprint(q,s):
    return hashlib.sha256(json.dumps([version(question_snapshot(q)),s.text if s else None,s.final_answer if s else None],sort_keys=True).encode()).hexdigest()

def flags(q,s):
    snap=question_snapshot(q); text='\n'.join([snap.get('passage') or '',snap['text'],*(o['text'] for o in snap['options'])]); reasons=[]
    if re.search(r'(?i)\b(?:section id|question paper name|display panel|group all questions|question shuffle allowed)\s*:',text):reasons.append('Internal exam metadata in question')
    tokens={i.get('token') for i in snap['images']}
    if any(m[1] not in tokens for m in TOKEN.finditer(text)):reasons.append('Image token has no matching active image')
    if len(re.sub(r'\s|\[\[IMAGE:[^\]]+\]\]','',text))<8 and not snap['images']:reasons.append('Very short or empty extracted question')
    if q.warnings:reasons.append('Extraction warnings: '+str(q.warnings)[:250])
    name=q.paper.course.name.casefold()
    if ('corporate finance' in name and re.search(r'(?i)semantic role labell?ing',text)) or ('reinforcement learning' in name and re.search(r'(?i)\bnet profit\b',text)):
        reasons.append('Possible course mismatch: compare with the original PDF')
    if s:
        if s.version!=version(snap):reasons.append('Outdated solution')
        if s.checks:reasons.extend(str(x) for x in s.checks)
        if snap.get('answers') is None:reasons.append('No source answer key to verify solution')
        else:
            try:
                if grade({**snap,'marks':1,'negative_marks':0},s.final_answer)['outcome']!='CORRECT':reasons.append('Solution final answer differs from source key')
            except (ValueError,TypeError,KeyError):reasons.append('Solution final answer cannot be checked')
        for a,b in ((r'\(',r'\)'),(r'\[',r'\]')):
            if s.text.count(a)!=s.text.count(b):reasons.append('Unbalanced LaTeX delimiters')
        if s.text.count('$$')%2:reasons.append('Unbalanced display maths delimiters')
    return list(dict.fromkeys(reasons))

@quality.get('/scan')
@require_user(True)
def scan():
    cursor=integer_argument('after') if 'after' in request.args else 0
    query=Question.query.join(Paper).filter(Paper.status!='ARCHIVED',Question.id>cursor)
    for arg,col in [('course_id',Paper.course_id),('paper_id',Paper.id)]:
        if request.args.get(arg):query=query.filter(col==integer_argument(arg))
    rows=query.options(selectinload(Question.options),selectinload(Question.images),selectinload(Question.paper).selectinload(Paper.course),selectinload(Question.paper).selectinload(Paper.term),selectinload(Question.paper).selectinload(Paper.exam_type)).order_by(Question.id).limit(201).all()
    more=len(rows)>200; rows=rows[:200]; ids=[q.id for q in rows]
    solutions={s.question_id:s for s in AISolution.query.filter(AISolution.question_id.in_(ids))}
    reviews={r.question_id:r for r in ContentQualityReview.query.filter(ContentQualityReview.question_id.in_(ids))}
    result=[];seen={}
    for q in rows:
        s=solutions.get(q.id); reasons=flags(q,s); key=(q.paper_id,re.sub(r'\s+',' ',q.text or '').strip().casefold())
        if len(key[1])>30 and key in seen:reasons.append('Possible duplicate of Q'+seen[key])
        seen[key]=q.number
        f=fingerprint(q,s); review=reviews.get(q.id); reviewed=bool(review and review.fingerprint==f)
        if reasons or (s and not reviewed) or request.args.get('all')=='1':
            result.append(dict(id=q.id,number=q.number,paper_id=q.paper_id,paper=paper_title(q.paper),status=q.status,flags=reasons,reviewed=reviewed,fingerprint=f,solution_status=s.status if s else None))
    return jsonify(items=result,scanned=len(rows),has_more=more,next_after=rows[-1].id if rows else cursor)

@quality.get('/questions/<int:id>')
@require_user(True)
def detail(id):
    from .exam_api import question_with_image_urls,prepare_image_paths,use_paper_image_delivery
    q=db.get_or_404(Question,id);s=AISolution.query.filter_by(question_id=id).first();snap=question_snapshot(q)
    use_paper_image_delivery(q.paper_id);prepare_image_paths([snap])
    return jsonify(question=question_with_image_urls(snap),solution=s.text if s else None,flags=flags(q,s),fingerprint=fingerprint(q,s),paper_id=q.paper_id,checks=CHECKS)

@quality.post('/questions/<int:id>/review')
@require_user(True)
def review(id):
    q=db.get_or_404(Question,id);s=AISolution.query.filter_by(question_id=id).first();b=body();f=fingerprint(q,s)
    if b.get('fingerprint')!=f:abort(409,description='Content changed. Reopen and review the current version.')
    checks=b.get('checks',{})
    if not isinstance(checks,dict) or any(checks.get(k) is not True for k in CHECKS):abort(400,description='Complete all four review checks first. For a question without a solution, verify the source answer and working yourself.')
    row=db.session.get(ContentQualityReview,id) or ContentQualityReview(question_id=id)
    row.fingerprint=f;row.checks={k:True for k in CHECKS};row.reviewed_at=time.time();db.session.add(row);db.session.commit()
    return jsonify(ok=True)

@quality.get('/courses/<int:id>')
@require_user(True)
def guide(id):
    c=db.get_or_404(Course,id); row=db.session.get(CourseGuide,id)
    from .course_guides import suggested_guide
    return jsonify(course=c.name,guide={k:getattr(row,k) for k in (*FIELDS,'published')} if row else {**suggested_guide(c),'published':False})

@quality.put('/courses/<int:id>')
@require_user(True)
def save_guide(id):
    db.get_or_404(Course,id);b=body();row=db.session.get(CourseGuide,id) or CourseGuide(course_id=id)
    for key in FIELDS:
        v=b.get(key,'')
        if not isinstance(v,str) or len(v)>6000:abort(400,description='Invalid guide '+key)
        setattr(row,key,v.strip())
    if type(b.get('published')) is not bool:abort(400,description='Choose draft or published')
    if b['published'] and any(not getattr(row,k) for k in FIELDS):abort(400,description='Complete all guide sections before publishing')
    row.published=b['published'];db.session.add(row);db.session.commit();return jsonify(ok=True)

@quality.put('/papers/<int:id>')
@require_user(True)
def settings(id):
    db.get_or_404(Paper,id);b=body();row=db.session.get(StudyPaperSettings,id) or StudyPaperSettings(paper_id=id)
    for key in ('featured','allow_ads'):
        if type(b.get(key)) is not bool:abort(400,description='Invalid paper setting')
        setattr(row,key,b[key])
    db.session.add(row);db.session.commit();return jsonify(ok=True)

@quality.get('/deployment')
@require_user(True)
def deployment():
    import os
    from pathlib import Path
    from .site_pages import origin
    manifest=Path(current_app.root_path).parent/'frontend/dist/.vite/manifest.json'
    assets=json.loads(manifest.read_text()) if manifest.exists() else {}
    return jsonify(public_origin=origin(),service_id=os.getenv('RENDER_SERVICE_ID','local'),repository=os.getenv('RENDER_GIT_REPO_SLUG','unknown'),branch=os.getenv('RENDER_GIT_BRANCH','unknown'),commit=os.getenv('RENDER_GIT_COMMIT','local'),app_asset=assets.get('index.html',{}).get('file'),note='Compare this commit with the intended GitHub main commit. This endpoint cannot inspect another Render account.')

@quality.get('/papers/<int:id>')
@require_user(True)
def get_settings(id):
    db.get_or_404(Paper,id);row=db.session.get(StudyPaperSettings,id)
    return jsonify(featured=bool(row and row.featured),allow_ads=bool(row and row.allow_ads))
