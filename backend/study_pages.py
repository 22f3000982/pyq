"""Read-only, server-rendered study pages; never create student attempts."""
import json
from pathlib import Path
from flask import Blueprint, render_template, abort, current_app, redirect, request
from sqlalchemy.orm import selectinload
from .models import db, Course, Paper, Question, QuestionImage, AISolution, AboutPage
from .about_api import data
from .engine import question_snapshot, question_order
from .ai_solutions import version
from .storage import image_url, send_asset
from .site_pages import metadata

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
    return page(c.name, f'Read {c.name} previous-year questions and available published explanations, or launch a practice test.', section='course', course=c, papers=papers)

@study.get('/study/papers/<int:id>')
def paper(id):
    p = Paper.query.options(selectinload(Paper.course), selectinload(Paper.term), selectinload(Paper.exam_type)).filter(Paper.id == id, Paper.status != 'ARCHIVED').first()
    if not p: abort(404)
    questions = Question.query.options(selectinload(Question.options), selectinload(Question.images)).filter_by(paper_id=id, status='AVAILABLE').all()
    if not questions: abort(404)
    questions.sort(key=lambda q: question_order(q.number))
    solutions = {s.question_id:s for s in AISolution.query.filter(AISolution.question_id.in_([q.id for q in questions]), AISolution.status == 'PUBLISHED').all()}
    items=[]
    for q in questions:
        snap=question_snapshot(q)
        s=solutions.get(q.id)
        items.append(dict(question=q, snapshot=snap, solution=s.text if s and s.version==version(snap) else None))
    return page(p.name, f'{p.course.name}: {p.exam_type.name}, {p.term.name}. Read questions and available published solutions.', section='paper', paper=p, items=items)

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

@study.get('/contact')
def contact():
    return page('Contact & content removal', 'Contact MauryaHub for support, corrections and copyright or content removal requests.', section='contact', about=data(db.session.get(AboutPage,1)))
