"""Private OPPE authoring and practice. No submitted code executes in Flask."""
import hashlib,json,os,re,time
import requests
from flask import Blueprint,abort,current_app,jsonify,request,send_from_directory
from .api import require_user,body
from .models import db
from . import limiter

bp=Blueprint('oppe',__name__,url_prefix='/api/admin/oppe')
@bp.get('/assets/<name>')
@require_user(True)
def question_asset(name):
    if not re.fullmatch(r'[a-f0-9]{64}\.(?:png|jpg)',name):abort(404)
    from pathlib import Path
    response=send_from_directory(Path(__file__).parent/'data/oppe/images',name)
    return response

LANGUAGES={'python','java','postgresql','shell'}
DEFAULTS=[('python','Python','python'),('dbms','DBMS','postgresql'),('pdsa','PDSA','python'),('java','Java','java'),('sc','SC — System Commands','shell')]

class OPPECourse(db.Model):
    __tablename__='oppe_course'
    id=db.Column(db.Integer,primary_key=True)
    slug=db.Column(db.String(60),unique=True,nullable=False)
    name=db.Column(db.String(100),nullable=False)
    language=db.Column(db.String(20),nullable=False)
    categories=db.Column(db.JSON,nullable=False,default=lambda:['OPPE1','OPPE2'])

class OPPEQuestion(db.Model):
    __tablename__='oppe_question'
    id=db.Column(db.Integer,primary_key=True)
    course_id=db.Column(db.ForeignKey('oppe_course.id'),nullable=False)
    external_id=db.Column(db.String(100),nullable=False)
    content=db.Column(db.JSON,nullable=False)
    status=db.Column(db.String(12),nullable=False,default='DRAFT')
    validation_hash=db.Column(db.String(64))
    updated_at=db.Column(db.Float,nullable=False,default=time.time)
    __table_args__=(db.UniqueConstraint('course_id','external_id',name='uq_oppe_course_external'),db.Index('ix_oppe_question_course_status','course_id','status'))


def clean_text(value,label,limit,required=False):
    if not isinstance(value,str) or len(value)>limit or (required and not value.strip()):
        abort(400,description=f'{label}: expected {"non-empty " if required else ""}text, maximum {limit} characters')
    return value

def fingerprint(content,language):
    return hashlib.sha256(json.dumps([language,content],sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def course_or_404(cid):
    if type(cid)!=int:abort(400,description='Choose an OPPE course')
    c=db.session.get(OPPECourse,cid)
    if not c:abort(404,description='OPPE course not found')
    return c

def question_or_404(qid):
    q=db.session.get(OPPEQuestion,qid)
    if not q:abort(404,description='OPPE question not found')
    return q

def course_json(c):return dict(id=c.id,slug=c.slug,name=c.name,language=c.language,categories=c.categories)

def checked_env(env):
    if not isinstance(env,dict) or len(env)>15:abort(400,description='Invalid case environment')
    for k,v in env.items():
        if not isinstance(k,str) or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,49}',k) or k in ('PATH','HOME','BASH_ENV','ENV','TMPDIR','PGOPTIONS') or k.startswith(('LD_','PYTHON','JAVA','OPPE_')):abort(400,description='Unsafe environment variable')
        clean_text(v,'Environment value',2000)
    return env

def checked_paths(paths):
    if not isinstance(paths,list) or len(paths)>50:abort(400,description='Invalid expected file list')
    for path in paths:
        if not isinstance(path,str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,150}',path) or path.startswith('/') or '..' in path.split('/'):abort(400,description='Unsafe expected file path')
    return paths

def checked_content(raw,course):
    if not isinstance(raw,dict):abort(400,description='Question must be an object')
    result={k:clean_text(raw.get(k,''),k,n,k in ('title','statement')) for k,n in [('title',180),('statement',20000),('topic',100),('starter_code',30000),('prefix',30000),('suffix',30000),('reference_solution',30000),('explanation',20000),('source',500),('setup_sql',30000)]}
    category=raw.get('category','OPPE1')
    if not isinstance(category,str) or category not in course.categories:abort(400,description='Choose a configured exam category')
    result['category']=category
    difficulty=raw.get('difficulty','Medium')
    if difficulty not in ('Easy','Medium','Hard'):abort(400,description='Invalid difficulty')
    result['difficulty']=difficulty
    # Fixed prefix/suffix are always composed server-side; students edit only the middle.
    result['format']='fill' if result['prefix'] or result['suffix'] else 'program'
    tests=raw.get('tests')
    if not isinstance(tests,list) or not 0<=len(tests)<=20:abort(400,description='Provide up to 20 test cases')
    result['tests']=[]
    for t in tests:
        if not isinstance(t,dict) or type(t.get('hidden',False))!=bool:abort(400,description='Invalid test case')
        files=t.get('files',{})
        if not isinstance(files,dict) or len(files)>10:abort(400,description='Maximum 10 fixture files per test')
        safe_files={}
        for path,text in files.items():
            if not isinstance(path,str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,100}',path) or path.startswith(('/','-')) or any(p in ('','..','.') for p in path.split('/')):abort(400,description='Use safe relative fixture paths')
            if path in ('main.py','Main.java','main.sh','query.sql','setup.sql'):abort(400,description='Fixture filename is reserved')
            safe_files[path]=clean_text(text,'Fixture',20000)
        result['tests'].append(dict(input=clean_text(t.get('input',''),'Test input',20000),expected=clean_text(t.get('expected',''),'Expected output',20000),hidden=t.get('hidden',False),files=safe_files,setup_sql=clean_text(t.get('setup_sql',''),'Test SQL setup',30000),environment=checked_env(t.get('environment',{})),expected_files=checked_paths(t.get('expected_files',[]))))
    timeout=raw.get('time_limit',3)
    if type(timeout)!=int or not 1<=timeout<=10:abort(400,description='Time limit must be 1–10 seconds')
    result['time_limit']=timeout
    entrypoint=raw.get('entrypoint','Main')
    if not isinstance(entrypoint,str) or not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]{0,79}',entrypoint):abort(400,description='Java entry class must be a valid simple identifier')
    result['entrypoint']=entrypoint
    mode=raw.get('execution_mode','stdin')
    if mode not in ('stdin','python-call','python-dispatch'):abort(400,description='Unsupported execution mode')
    function=raw.get('entry_function','')
    if not isinstance(function,str) or (mode in ('python-call','python-dispatch') and (course.language!='python' or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,99}',function))):abort(400,description='Choose a valid Python entry function')
    result['execution_mode']=mode;result['entry_function']=function
    functions=raw.get('entry_functions',[])
    if not isinstance(functions,list) or len(functions)>30 or any(not isinstance(f,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,99}',f) for f in functions):abort(400,description='Invalid function allowlist')
    if mode=='python-dispatch' and not functions:abort(400,description='Dispatch needs an explicit function allowlist')
    result['entry_functions']=functions
    comparison=raw.get('comparison','text')
    if comparison not in ('text','python-value'):abort(400,description='Unsupported comparison')
    result['comparison']=comparison
    issues=raw.get('import_notes',[])
    if not isinstance(issues,list) or len(issues)>15:abort(400,description='Invalid import notes')
    result['import_notes']=[clean_text(note,'Import note',500) for note in issues]
    if len(json.dumps(result))>500000:abort(413)
    return result

def author_json(q):
    c=course_or_404(q.course_id)
    return dict(id=q.id,course_id=q.course_id,external_id=q.external_id,status=q.status,content=q.content,revision=fingerprint(q.content,c.language),validated=q.validation_hash==fingerprint(q.content,c.language))

def require_revision(q,b):
    if b.get('revision')!=fingerprint(q.content,course_or_404(q.course_id).language):abort(409,description='Question changed. Reload before continuing.')

def runner(code,content,language,tests):
    url=current_app.config.get('OPPE_RUNNER_URL') or os.getenv('OPPE_RUNNER_URL','')
    token=current_app.config.get('OPPE_RUNNER_TOKEN') or os.getenv('OPPE_RUNNER_TOKEN','')
    if not url or not token:abort(503,description='OPPE runner is not configured. Authoring and preview remain available.')
    if not url.startswith(('https://','http://127.0.0.1:','http://localhost:')):abort(503,description='Runner requires HTTPS (or localhost for development)')
    try:
        r=requests.post(url.rstrip('/')+'/execute',headers={'Authorization':'Bearer '+token},json=dict(language=language,code=content['prefix']+code+content['suffix'],setup_sql=content['setup_sql'],entrypoint=content.get('entrypoint','Main'),execution_mode=content.get('execution_mode','stdin'),entry_function=content.get('entry_function',''),entry_functions=content.get('entry_functions',[]),comparison=content.get('comparison','text'),tests=tests,time_limit=content['time_limit']),timeout=(5,min(600,len(tests)*(content['time_limit']+15)+10)),allow_redirects=False)
        if r.status_code==429:abort(429,description='OPPE runner is busy. Please retry shortly.')
        if r.status_code!=200:abort(503,description='OPPE runner unavailable. Check runner logs.')
        result=r.json()
        if not isinstance(result,dict) or not isinstance(result.get('results'),list) or len(result['results'])!=len(tests):raise ValueError('Invalid runner result')
        for item in result['results']:
            if not isinstance(item,dict) or type(item.get('passed'))!=bool:raise ValueError('Invalid test result')
        return result['results']
    except (requests.RequestException,ValueError):abort(503,description='OPPE execution failed. Please retry; your code has been preserved.')

@bp.get('/courses')
@require_user(True)
def courses():
    rows=OPPECourse.query.order_by(OPPECourse.id).all()
    counts=dict(db.session.query(OPPEQuestion.course_id,db.func.count(OPPEQuestion.id)).group_by(OPPEQuestion.course_id))
    return jsonify(items=[dict(**course_json(c),question_count=counts.get(c.id,0)) for c in rows],admin_only=True,runner_configured=bool((current_app.config.get('OPPE_RUNNER_URL') or os.getenv('OPPE_RUNNER_URL')) and (current_app.config.get('OPPE_RUNNER_TOKEN') or os.getenv('OPPE_RUNNER_TOKEN'))))

@bp.post('/courses/defaults')
@require_user(True)
def defaults():
    for slug,name,language in DEFAULTS:
        if not OPPECourse.query.filter_by(slug=slug).first():db.session.add(OPPECourse(slug=slug,name=name,language=language,categories=['OPPE1','OPPE2']))
    db.session.commit()
    return jsonify(ok=True)

@bp.post('/courses')
@require_user(True)
def add_course():
    b=body();slug=b.get('slug','');name=clean_text(b.get('name'),'Course name',100,True)
    if not isinstance(slug,str) or not re.fullmatch('[a-z][a-z0-9-]{0,59}',slug):abort(400,description='Use a lowercase course slug')
    if not isinstance(b.get('language'),str) or b.get('language') not in LANGUAGES:abort(400,description='Unsupported execution language')
    categories=b.get('categories',['OPPE1','OPPE2'])
    if not isinstance(categories,list) or not 1<=len(categories)<=10 or len(set(map(str,categories)))!=len(categories):abort(400,description='Provide distinct exam categories')
    for c in categories:clean_text(c,'Category',40,True)
    c=OPPECourse(slug=slug,name=name,language=b['language'],categories=categories);db.session.add(c);db.session.commit()
    return jsonify(course_json(c)),201

@bp.get('/questions')
@require_user(True)
def questions():
    query=OPPEQuestion.query
    cid=request.args.get('course_id',type=int)
    if cid:query=query.filter_by(course_id=cid)
    rows=query.order_by(OPPEQuestion.id).all()
    search=request.args.get('q','').casefold();category=request.args.get('category','');status=request.args.get('status','')
    items=[]
    for q in rows:
        d=q.content
        if search and search not in (d['title']+' '+d['topic']).casefold():continue
        if category and d['category']!=category:continue
        if status and q.status!=status:continue
        items.append(dict(id=q.id,course_id=q.course_id,title=d['title'],topic=d['topic'],category=d['category'],difficulty=d['difficulty'],status=q.status))
    return jsonify(items=items)

@bp.get('/questions/<int:qid>')
@require_user(True)
def detail(qid):
    q=question_or_404(qid);d=q.content;c=course_or_404(q.course_id)
    # Author data uses a separate endpoint; practice never receives hidden tests/answers.
    public={k:d[k] for k in ('title','statement','topic','category','difficulty','starter_code','prefix','suffix','source','time_limit','entrypoint','execution_mode','entry_function','entry_functions','comparison','import_notes')}
    # Seed bundles predate this derived display field; never require it in stored JSON.
    public['format']='fill' if d.get('prefix') or d.get('suffix') else 'program'
    public['samples']=[dict(input=t['input'],expected=t['expected'],files=t['files'],environment=t.get('environment',{}),expected_files=t.get('expected_files',[])) for t in d['tests'] if not t['hidden']]
    return jsonify(id=q.id,course=course_json(c),question=public,revision=fingerprint(d,c.language),status=q.status,submission_ready=any(t['hidden'] for t in d['tests']))

@bp.get('/questions/<int:qid>/author')
@require_user(True)
def author(qid):return jsonify(author_json(question_or_404(qid)))

@bp.post('/questions')
@require_user(True)
def create_question():
    b=body();c=course_or_404(b.get('course_id'));external=clean_text(b.get('external_id'),'External ID',100,True)
    q=OPPEQuestion(course_id=c.id,external_id=external,content=checked_content(b.get('content'),c));db.session.add(q);db.session.commit()
    return jsonify(author_json(q)),201

@bp.put('/questions/<int:qid>')
@require_user(True)
def edit(qid):
    b=body();q=OPPEQuestion.query.filter_by(id=qid).with_for_update().first_or_404();require_revision(q,b)
    q.content=checked_content(b.get('content'),course_or_404(q.course_id));q.status='DRAFT';q.validation_hash=None;q.updated_at=time.time();db.session.commit()
    return jsonify(author_json(q))

@bp.post('/questions/<int:qid>/validate')
@limiter.limit('6 per minute')
@require_user(True)
def validate(qid):
    b=body();q=question_or_404(qid);require_revision(q,b);d=q.content;c=course_or_404(q.course_id);version=fingerprint(d,c.language)
    # Release DB connection before slow isolated execution.
    if not d['reference_solution'].strip() or not any(not t['hidden'] for t in d['tests']) or not any(t['hidden'] for t in d['tests']):abort(409,description='Reference code, at least one sample and one real hidden test are required for validation. This import remains a draft.')
    code=d['reference_solution'];language=c.language;db.session.rollback()
    results=runner(code,d,language,d['tests']);passed=all(t['passed'] for t in results)
    q=OPPEQuestion.query.filter_by(id=qid).with_for_update().first_or_404()
    if fingerprint(q.content,course_or_404(q.course_id).language)!=version:abort(409,description='Question changed during validation')
    q.validation_hash=version if passed else None;q.status='DRAFT';db.session.commit()
    return jsonify(passed=passed,results=results)

@bp.post('/questions/<int:qid>/publish')
@require_user(True)
def publish(qid):
    b=body();q=OPPEQuestion.query.filter_by(id=qid).with_for_update().first_or_404();require_revision(q,b)
    if q.validation_hash!=fingerprint(q.content,course_or_404(q.course_id).language):abort(409,description='Validate the current reference solution against every test first')
    q.status='READY';db.session.commit();return jsonify(ok=True,status='READY',admin_only=True)

@bp.post('/questions/<int:qid>/execute')
@limiter.limit('12 per minute')
@require_user(True)
def execute(qid):
    b=body();q=question_or_404(qid);require_revision(q,b);code=clean_text(b.get('code'),'Code',30000,True);action=b.get('action')
    if action not in ('run','submit','custom'):abort(400,description='Choose Run, Submit or Custom input')
    d=q.content;c=course_or_404(q.course_id);language=c.language
    tests=d['tests'] if action=='submit' else [t for t in d['tests'] if not t['hidden']]
    if action=='custom':tests=[dict(input=clean_text(b.get('input',''),'Custom input',20000),expected='',hidden=False,files={})]
    if any(t.get('expected_files') for t in tests):abort(409,description='This question needs a file-system result checker; it remains an archived draft and cannot be graded by stdout alone.')
    if not tests:abort(409,description='No test cases available. Add samples before running this draft.')
    if action=='submit' and not any(t['hidden'] for t in tests):abort(409,description='Hidden tests are missing. Run samples for now; full submission is not ready.')
    db.session.rollback()
    results=runner(code,d,language,tests);safe=[]
    for i,(test,r) in enumerate(zip(tests,results)):
        row=dict(number=i+1,hidden=test['hidden'],passed=r['passed'] if action!='custom' else None,status=str(r.get('status','Execution error'))[:60],duration_ms=r.get('duration_ms'))
        if action=='custom' and row['status'] in ('Accepted','Wrong answer'):row['status']='Completed'
        if not test['hidden']:row.update(input=test['input'],expected=test['expected'] if action!='custom' else None,output=str(r.get('output',''))[:20000],error=str(r.get('error',''))[:4000])
        safe.append(row)
    return jsonify(results=safe,passed=sum(r['passed'] for r in results) if action!='custom' else None,total=len(results),action=action)

@bp.get('/questions/<int:qid>/solution')
@require_user(True)
def solution(qid):
    d=question_or_404(qid).content;return jsonify(code=d['reference_solution'],explanation=d['explanation'])

@bp.get('/template')
@require_user(True)
def template():
    slug=request.args.get('course_slug','python')
    c=OPPECourse.query.filter_by(slug=slug).first()
    if not c:abort(404,description='OPPE course not found')
    demos={
        'python':('Sum two integers','Read two integers separated by whitespace and print their sum.','a, b = map(int, input().split())\n# Print the sum\n','a, b = map(int, input().split())\nprint(a + b)\n','2 3\n','5\n','-4 9\n','5\n','Input and arithmetic','**1. Read the values.** Split the input and convert each value to an integer.\n\n**2. Add and print.** `a + b` calculates the sum; `print` writes it to standard output.'),
        'pdsa':('Count distinct integers','Read a space-separated line of integers. Print how many distinct values it contains.','numbers = list(map(int, input().split()))\n# Count distinct values\n','numbers = list(map(int, input().split()))\nprint(len(set(numbers)))\n','3 1 3 2 1\n','3\n','-1 -1 0 7\n','3\n','Sets','**1. Read the integers.** Build a list from the input.\n\n**2. Remove duplicates.** A set stores each distinct integer once.\n\n**3. Count.** `len(set(numbers))` gives the required count. Expected time is O(n), with O(k) extra space for k distinct values.'),
        'java':('Add two long integers','Read two long integers and print their sum. Use class Main.','import java.util.Scanner;\npublic class Main {\n public static void main(String[] args) {\n  Scanner s = new Scanner(System.in);\n  // Read and add the two values\n }\n}\n','import java.util.Scanner;\npublic class Main {\n public static void main(String[] args) {\n  Scanner s = new Scanner(System.in);\n  long a=s.nextLong(), b=s.nextLong();\n  System.out.println(a+b);\n }\n}\n','2 3\n','5\n','3000000000 -1\n','2999999999\n','Input and numeric types','**1. Read with Scanner.** `nextLong()` accepts integers outside the int range.\n\n**2. Add using long.** Both operands are long, so their sum uses long arithmetic.\n\n**3. Print the sum.** Do not print prompts, since stdout is compared with the expected answer.'),
        'dbms':('Employees above a salary threshold','The employees(id, name, salary) table is provided. Select names with salary >= 50000, ordered by id. Return only the name column.','SELECT -- complete the query\n','SELECT name FROM employees WHERE salary >= 50000 ORDER BY id;\n','','Asha\nDev\n','','Nila\n','Filtering and ordering','**1. Filter rows.** `WHERE salary >= 50000` includes the threshold itself.\n\n**2. Select the requested column.** Return name, without id or salary.\n\n**3. Order deterministically.** `ORDER BY id` ensures the expected row order.'),
        'sc':('Sort and remove duplicate lines','Read lines from standard input. Print distinct lines in ascending byte order. Use the C locale.','# Write a Bash pipeline\n','LC_ALL=C sort -u\n','pear\napple\npear\n','apple\npear\n','z\na\nz\nb\n','a\nb\nz\n','Pipelines and sorting','**1. Sort the input.** `sort` reads standard input.\n\n**2. Fix the locale.** `LC_ALL=C` gives deterministic byte ordering.\n\n**3. Remove repeated lines.** The `-u` flag emits each equal line once.')}
    key=slug if slug in demos else {'python':'python','java':'java','postgresql':'dbms','shell':'sc'}[c.language]
    title,statement,starter,reference,inp,out,hin,hout,topic,explanation=demos[key]
    tests=[dict(input=inp,expected=out,hidden=False,files={}),dict(input=hin,expected=hout,hidden=True,files={})]
    setup=''
    if c.language=='postgresql':
        setup="CREATE TABLE employees(id integer PRIMARY KEY,name text,salary integer); INSERT INTO employees VALUES(1,'Asha',50000),(2,'Ben',49000),(3,'Dev',80000);"
        # Each case can reset data through an isolated setup file read by the query wrapper.
        tests[1]['setup_sql']="CREATE TABLE employees(id integer PRIMARY KEY,name text,salary integer); INSERT INTO employees VALUES(1,'Nila',70000),(2,'Sam',49999);"
        statement+='\n\nSample table:\n\n| id | name | salary |\n|---|---|---|\n| 1 | Asha | 50000 |\n| 2 | Ben | 49000 |\n| 3 | Dev | 80000 |'
    content=dict(title=title,statement=statement,topic=topic,category=c.categories[0],difficulty='Easy',starter_code=starter,prefix='',suffix='',reference_solution=reference,explanation=explanation,source='Original MauryaHub demonstration',setup_sql=setup,time_limit=3,tests=tests)
    return jsonify(format='mauryahub-oppe-v1',course_slug=slug,questions=[dict(external_id='original-demo-v1',content=content)])


@bp.post('/import')
@require_user(True)
def import_questions():
    b=body();bundle=b.get('bundle')
    if not isinstance(bundle,dict) or bundle.get('format')!='mauryahub-oppe-v1':abort(400,description='Use mauryahub-oppe-v1 JSON')
    if len(json.dumps(bundle))>3000000:abort(413)
    c=OPPECourse.query.filter_by(slug=bundle.get('course_slug')).first()
    if not c:abort(400,description='Create the course before import')
    rows=bundle.get('questions')
    if not isinstance(rows,list) or not 1<=len(rows)<=50:abort(400,description='Import 1–50 questions at a time')
    checked=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):abort(400,description='Invalid question object')
        external=clean_text(row.get('external_id'),'External ID',100,True)
        if external in seen:abort(400,description='Duplicate external ID in import')
        seen.add(external);content=checked_content(row.get('content'),c)
        old=OPPEQuestion.query.filter_by(course_id=c.id,external_id=external).with_for_update().first()
        if old and b.get('overwrite') is not True:abort(409,description=f'{external} already exists. Enable overwrite to replace it.')
        checked.append((external,content,old))
    if b.get('save') is True:
        for external,content,old in checked:
            q=old or OPPEQuestion(course_id=c.id,external_id=external)
            q.content=content;q.status='DRAFT';q.validation_hash=None;q.updated_at=time.time();db.session.add(q)
        db.session.commit()
    return jsonify(saved=len(checked) if b.get('save') is True else 0,items=[dict(external_id=e,title=d['title'],replacing=old is not None) for e,d,old in checked])
