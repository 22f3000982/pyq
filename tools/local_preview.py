"""Run the complete app with isolated demo data; never uses production services."""
import os, sys, threading, json, urllib.request, http.cookiejar, subprocess, secrets, webbrowser
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for key in ('RENDER', 'FLASK_ENV', 'APP_ENV', 'DATABASE_URL', 'REDIS_URL', 'IMAGE_CDN_BASE_URL', 'IMAGE_CDN_MANIFEST'):
    os.environ.pop(key, None)
from backend import create_app
from backend.models import db, Course, Term, ExamType, Paper, Question, QuestionOption, User
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server
folder = Path(__file__).resolve().parents[1]/'.local-demo'
folder.mkdir(exist_ok=True)
os.environ.update(PYTHON_DOTENV_DISABLED='1', STORAGE_BACKEND='local', COOKIE_SECURE='false', IMAGE_DELIVERY='proxy', RATELIMIT_STORAGE_URI='memory://', CATALOG_AUTO_PROCESS='false', SECRET_KEY=secrets.token_hex(32), DATABASE_URL='sqlite:///'+(folder/'preview.db').as_posix(), UPLOAD_DIR=str(folder/'uploads'))
app = create_app({'TESTING': True, 'STORAGE_BACKEND': 'local', 'IMAGE_DELIVERY': 'proxy', 'CONTENT_CACHE_URL': '', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(folder/'preview.db'), 'UPLOAD_DIR': str(folder/'uploads'), 'SESSION_COOKIE_SECURE': False, 'RATELIMIT_ENABLED': False, 'CATALOG_AUTO_PROCESS': False})
with app.app_context():
    db.create_all()
    paper=db.session.execute(db.select(Paper).where(Paper.identity=='local-demo')).scalar_one_or_none()
    if paper is None:
        course=Course(name='LOCAL DEMO — Scratch board test',code='LOCAL')
        term=Term(name='Local 2026',year=2026,month=1)
        exam=ExamType(name='Quiz 1')
        db.session.add_all([course,term,exam]);db.session.flush()
        paper=Paper(identity='local-demo',course_id=course.id,term_id=term.id,exam_type_id=exam.id,name='LOCAL DEMO — Sample exam',duration_seconds=3600,status='AVAILABLE')
        db.session.add(paper);db.session.flush()
        for n in range(1,6):
            question=Question(paper_id=paper.id,number=str(n),kind='MCQ',text=f'Local demo question {n}: what is 2 + 2?',answers=['B'],answer_status='ANSWER_AVAILABLE',marks=1,negative_marks=0,status='AVAILABLE')
            question.options=[QuestionOption(key='A',text='3',position=0),QuestionOption(key='B',text='4',position=1)]
            db.session.add(question)
        db.session.commit()
    paper_id=paper.id
    if not db.session.execute(db.select(User).where(User.email=='admin@local.test')).scalar_one_or_none():
        db.session.add(User(email='admin@local.test',name='Local Admin',role='ADMIN',password_hash=generate_password_hash('local-preview-123')));db.session.commit()
port=int(os.environ.get('PYQ_LOCAL_PORT','5000'))
server=make_server('127.0.0.1',port,app,threaded=True)
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{port}'
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def get(path):
    with client.open(base+path) as r:return r.status,r.read()
assert get('/')[0]==200
assert json.loads(get('/healthz')[1])['status']=='ok'
csrf=json.loads(get('/api/session')[1])['csrf']
assert get('/api/papers')[0]==200
request=urllib.request.Request(base+'/api/attempts',data=json.dumps({'paper_id':paper_id,'mode':'exam'}).encode(),headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
with client.open(request) as response:
    assert response.status==201
    attempt=json.load(response)
assert get(f"/api/attempts/{attempt['id']}/questions/{attempt['palette'][0]['question_id']}")[0]==200
print(f'Complete Vue + Flask app running at {base}. Home, database, papers, guest exam start and question loading verified. Demo data only.',flush=True)
print('Local admin: admin@local.test / local-preview-123 (local demo only)',flush=True)
worker=subprocess.Popen([sys.executable,'-m','flask','--app','backend:create_app','worker'],cwd=Path(__file__).resolve().parents[1],env=os.environ.copy())
if '--no-browser' not in sys.argv:webbrowser.open(base)
try:threading.Event().wait()
except KeyboardInterrupt:pass
finally:
    server.shutdown();worker.terminate()
    try:worker.wait(timeout=5)
    except subprocess.TimeoutExpired:worker.kill()
