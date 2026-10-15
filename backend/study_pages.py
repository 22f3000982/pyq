"""Read-only, server-rendered study pages; never create student attempts."""
import json
from pathlib import Path
from flask import Blueprint, render_template, abort, current_app, redirect, request
from sqlalchemy.orm import selectinload
from .models import db, Course, Paper, Question, QuestionImage, AISolution, AboutPage, CourseGuide, StudyPaperSettings, ContentQualityReview
from .about_api import data
from .engine import question_snapshot, question_order
from .ai_solutions import version
from .storage import image_url, send_asset
from .site_pages import metadata
from .public_content import paper_title, paper_items
from .course_guides import suggested_guide

study = Blueprint('study', __name__)

def available():
    return db.session.query(Question.paper_id).filter(Question.status == 'AVAILABLE')

def page(title, description, **values):
    manifest = Path(current_app.root_path).parent / 'frontend/dist/.vite/manifest.json'
    assets = {}
    if manifest.exists():
        assets = json.loads(manifest.read_text()).get('src/study.js', {})
    return render_template('study.html', title=title, description=description, assets=assets, **metadata(), search=request.args.get('q','').strip()[:150], **values)

@study.get('/study')
def library():
    ids = db.session.query(Paper.course_id).filter(Paper.status != 'ARCHIVED', Paper.id.in_(available()))
    courses = Course.query.filter(Course.id.in_(ids)).order_by(Course.name).all()
    search=request.args.get('q','').strip().casefold()[:150]
    if search:courses=[c for c in courses if search in ' '.join([c.name,c.code or '',c.level or '',*(c.aliases or [])]).casefold()]
    return page('Study library', 'Browse IITM BS previous-year questions by course. Read without signing in or starting an exam.', section='library', courses=courses)

@study.get('/study/courses/<int:id>')
def course(id):
    c = db.session.get(Course, id)
    if not c: abort(404)
    papers = Paper.query.options(selectinload(Paper.term), selectinload(Paper.exam_type)).filter(Paper.course_id == id, Paper.status != 'ARCHIVED', Paper.id.in_(available())).order_by(Paper.id.desc()).all()
    if not papers: abort(404)
    search=request.args.get('q','').strip().casefold()[:150]
    if search:papers=[p for p in papers if search in ' '.join([p.name,p.term.name,p.exam_type.name,p.session or '']).casefold()]
    return page(c.name, f'Read {c.name} previous-year questions and available published explanations, or launch a practice test.', section='course', course=c, papers=papers, paper_title=paper_title, guide=public_guide(c), coverage=solution_coverage([p.id for p in papers]))

@study.get('/study/papers/<int:id>')
def paper(id):
    p = Paper.query.options(selectinload(Paper.course), selectinload(Paper.term), selectinload(Paper.exam_type)).filter(Paper.id == id, Paper.status != 'ARCHIVED').first()
    if not p: abort(404)
    questions = Question.query.options(selectinload(Question.options), selectinload(Question.images)).filter_by(paper_id=id, status='AVAILABLE').all()
    if not questions: abort(404)
    questions.sort(key=lambda q: question_order(q.number))
    solutions = {s.question_id:s for s in AISolution.query.filter(AISolution.question_id.in_([q.id for q in questions]), AISolution.status == 'PUBLISHED').all()}
    items=paper_items(questions,solutions)
    published=sum(bool(i['solution']) for i in items)
    from .advertising import ad_context
    return page(paper_title(p), f'{p.course.name}: {p.exam_type.name}, {p.term.name}. {len(items)} questions and {published} published explanations.', section='paper', paper=p, items=items, published_count=published, advertising=ad_context(p,questions,solutions))

@study.get('/study/images/<int:id>')
def image(id):
    row = db.session.query(QuestionImage, Question).join(Question).join(Paper, Paper.id==Question.paper_id).filter(QuestionImage.id==id, Question.status=='AVAILABLE', Paper.status!='ARCHIVED').first()
    if not row: abort(404)
    image,q=row
    if not any(i['id']==id for i in question_snapshot(q)['images']): abort(404)
    url=image_url(image.path,image.id)
    if not url.startswith('/api/images/'):
        return redirect(url,302)
    return send_asset(image.path,mimetype='image/png',conditional=True)

from . import limiter
from .contact import public_contact

@study.route('/contact', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def contact():
    return public_contact()


def public_guide(course):
    guide=db.session.get(CourseGuide,course.id)
    if guide:
        return guide if guide.published else None
    # Original revision guidance is shown with no claim of official curriculum coverage.
    suggested=suggested_guide(course)
    return suggested if suggested['introduction'] else None

def solution_coverage(paper_ids):
    if not paper_ids:return {}
    from sqlalchemy import func
    totals=dict(db.session.query(Question.paper_id,func.count(Question.id)).filter(Question.paper_id.in_(paper_ids),Question.status=='AVAILABLE').group_by(Question.paper_id))
    rows=db.session.query(Question,AISolution).join(AISolution,AISolution.question_id==Question.id).options(selectinload(Question.options),selectinload(Question.images)).filter(Question.paper_id.in_(paper_ids),Question.status=='AVAILABLE',AISolution.status=='PUBLISHED').all()
    counts={pid:0 for pid in paper_ids}
    for q,s in rows:
        if s.version==version(question_snapshot(q)):counts[q.paper_id]+=1
    return {pid:dict(total=total,published=counts.get(pid,0)) for pid,total in totals.items()}

@study.get('/study/featured')
def featured():
    # Editors explicitly select papers; current coverage is verified before display.
    papers=Paper.query.join(StudyPaperSettings,StudyPaperSettings.paper_id==Paper.id).options(selectinload(Paper.course),selectinload(Paper.term),selectinload(Paper.exam_type)).filter(StudyPaperSettings.featured.is_(True),Paper.status=='AVAILABLE').order_by(Paper.id.desc()).limit(12).all()
    coverage=solution_coverage([p.id for p in papers])
    papers=[p for p in papers if coverage.get(p.id,{}).get('published',0)>0]
    return page('Featured study papers','Read selected papers and their published explanations without starting an exam.',section='featured',papers=papers,paper_title=paper_title,coverage=coverage)

@study.get('/api/study-featured')
def featured_data():
    from flask import jsonify
    papers=Paper.query.join(StudyPaperSettings,StudyPaperSettings.paper_id==Paper.id).options(selectinload(Paper.course),selectinload(Paper.term),selectinload(Paper.exam_type)).filter(StudyPaperSettings.featured.is_(True),Paper.status=='AVAILABLE').order_by(Paper.id.desc()).limit(6).all()
    coverage=solution_coverage([p.id for p in papers])
    return jsonify(items=[dict(id=p.id,title=paper_title(p),**coverage[p.id]) for p in papers if coverage.get(p.id,{}).get('published',0)>0]),200,{'Cache-Control':'public, max-age=60'}
