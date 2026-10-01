"""Regressions for catalog query growth, secure question bundles and production guards."""
import pytest
from sqlalchemy import event
from backend.models import db,Course,Term,ExamType,Paper,Question,QuestionOption,QuestionImage,User,Attempt
from conftest import login

def seed(n=12):
    t=Term(name='Stability term',year=2026,month=5);e=ExamType(name='Stability exam')
    db.session.add_all([t,e]);db.session.flush()
    ids=[]
    for i in range(n):
        c=Course(name=f'Course {i}',code=f'C{i}');db.session.add(c);db.session.flush()
        p=Paper(identity=f'stable-{i}',name=f'Paper {i}',course_id=c.id,term_id=t.id,exam_type_id=e.id,status='AVAILABLE',duration_seconds=5400)
        db.session.add(p);db.session.flush()
        for number in ['10','2']:
            q=Question(paper_id=p.id,number=number,kind='MCQ',text=r'Value \(x^{2}\) [[IMAGE:formula]]',status='AVAILABLE',answers=['b'],answer_status='ANSWER_AVAILABLE',marks=2,negative_marks=0,explanation='Source explanation')
            db.session.add(q);db.session.flush()
            db.session.add_all([QuestionOption(question_id=q.id,key='a',text='Alpha',position=0),QuestionOption(question_id=q.id,key='b',text='Beta',position=1),QuestionImage(question_id=q.id,path='formula.png',alt='Source formula')])
        ids.append(p.id)
    db.session.commit();return ids

def query_count(client,url):
    queries=[]
    def record(conn,cursor,statement,*args):
        if statement.lstrip().upper().startswith('SELECT'):queries.append(statement)
    event.listen(db.engine,'before_cursor_execute',record)
    try:response=client.get(url)
    finally:event.remove(db.engine,'before_cursor_execute',record)
    assert response.status_code==200,response.json
    return response.json,len(queries)

def test_catalog_and_papers_have_bounded_queries(app,client):
    seed()
    catalog,count=query_count(client,'/api/catalog')
    assert len(catalog['courses'])==12 and catalog['meta']['terms']
    assert all(c['exams']=={'Stability exam':1} for c in catalog['courses'])
    assert count<=8
    courses,count=query_count(client,'/api/courses?limit=100');assert count<=5
    assert courses['items'][0]['question_count']==2
    papers,count=query_count(client,'/api/papers?limit=100');assert count<=5
    assert len(papers['items'])==12 and all(p['total_marks']==4 for p in papers['items'])

def test_bundle_ownership_no_keys_natural_order_and_no_r2_calls(app,client,monkeypatch):
    pid=seed(1)[0];h=login(client)
    a=client.post('/api/attempts',json={'paper_id':pid,'mode':'exam'},headers=h).json
    # Generating a question bundle must not perform any object storage requests.
    monkeypatch.setattr('backend.storage.client',lambda:pytest.fail('Unexpected R2 client call'))
    bundle=client.get(f"/api/attempts/{a['id']}/questions");assert bundle.status_code==200
    assert [i['question']['number'] for i in bundle.json['items']]==['2','10']
    for item in bundle.json['items']:
        assert not {'answers','answer_status','explanation','tolerance','evidence'}&item['question'].keys()
        assert 'feedback' not in item
        assert '[[IMAGE:formula]]' in item['question']['text']
        assert item['question']['images'][0]['url'].startswith('/api/images/')
    other=app.test_client();assert other.get(f"/api/attempts/{a['id']}/questions").status_code==404
    db.session.add(User(email='other@example.test',name='Other',password_hash='unused'));db.session.commit()
    with other.session_transaction() as sess:sess['uid']=User.query.filter_by(email='other@example.test').one().id
    assert other.get(f"/api/attempts/{a['id']}/questions").status_code==404

def test_image_proxy_auth_cache_and_missing_content(app,client,tmp_path):
    seed(1);image=QuestionImage.query.first()
    from backend.storage import local_path
    path=local_path(image.path);path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(b'PNG')
    assert client.get(f'/api/images/{image.id}').status_code==200
    login(client);r=client.get(f'/api/images/{image.id}')
    assert r.status_code==200 and r.data==b'PNG'
    assert r.headers['Cache-Control']=='private, max-age=31536000, immutable'
    assert 'Cookie' in r.headers['Vary']
    assert client.get(f'/api/images/{image.id}',headers={'If-None-Match':r.headers['ETag']}).status_code==304
    path.unlink();assert client.get(f'/api/images/{image.id}').status_code==404

@pytest.mark.parametrize('uri,storage,message',[
    ('sqlite://','r2','PostgreSQL'),
    ('postgresql+psycopg://u:p@host/db','local','R2 storage'),
])
def test_production_rejects_fallback(monkeypatch,tmp_path,uri,storage,message):
    from backend import create_app
    monkeypatch.setenv('APP_ENV','production')
    with pytest.raises(RuntimeError,match=message):create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':uri,'STORAGE_BACKEND':storage,'UPLOAD_DIR':str(tmp_path)})
