from copy import deepcopy
from conftest import login
from backend.oppe import OPPEQuestion
from backend.models import db

BASE='/api/admin/oppe'
def setup(client):
    h=login(client,True)
    assert client.post(BASE+'/courses/defaults',json={},headers=h).status_code==200
    bundle=client.get(BASE+'/template').json
    return h,bundle

def create(client,h,bundle):
    r=client.post(BASE+'/import',json={'bundle':bundle,'save':True},headers=h)
    assert r.status_code==200,r.json
    qid=client.get(BASE+'/questions').json['items'][0]['id']
    return qid,client.get(f'{BASE}/questions/{qid}/author').json

def test_oppe_private_and_csrf(client):
    for path in ('courses','questions','template','questions/1','questions/1/author','questions/1/solution'):
        assert client.get(BASE+'/'+path).status_code==401
    assert client.post(BASE+'/courses/defaults',json={}).status_code==403
    h,b=setup(client)
    assert [c['slug'] for c in client.get(BASE+'/courses').json['items']]==['python','dbms','pdsa','java','sc']
    assert client.post(BASE+'/courses/defaults',json={},headers=h).status_code==200
    assert len(client.get(BASE+'/courses').json['items'])==5

def test_import_preview_atomic_and_overwrite(client):
    h,b=setup(client)
    assert client.post(BASE+'/import',json={'bundle':b},headers=h).json['saved']==0
    assert client.get(BASE+'/questions').json['items']==[]
    bad=deepcopy(b);bad['questions'].append({'external_id':'broken','content':{}})
    assert client.post(BASE+'/import',json={'bundle':bad,'save':True},headers=h).status_code==400
    assert client.get(BASE+'/questions').json['items']==[]
    qid,a=create(client,h,b)
    assert client.post(BASE+'/import',json={'bundle':b,'save':True},headers=h).status_code==409
    r=client.post(BASE+'/import',json={'bundle':b,'save':True,'overwrite':True},headers=h)
    assert r.json['saved']==1
    assert client.get(f'{BASE}/questions/{qid}/author').json['status']=='DRAFT'

def test_practice_payload_hides_reference_and_hidden_tests(client):
    h,b=setup(client);qid,a=create(client,h,b)
    d=client.get(f'{BASE}/questions/{qid}').json
    assert len(d['question']['samples'])==1
    assert all(k not in d['question'] for k in ('reference_solution','tests','setup_sql','explanation'))
    assert 'print(a + b)' not in str(d)
    r=client.post(f'{BASE}/questions/{qid}/execute',json={'revision':d['revision'],'code':'print(5)','action':'run'},headers=h)
    assert r.status_code==503 and 'not configured' in r.json['error']

def test_validation_publish_revision_and_hidden_results(client,app,monkeypatch):
    import backend.oppe as module
    h,b=setup(client);qid,a=create(client,h,b)
    assert client.post(f'{BASE}/questions/{qid}/publish',json={'revision':a['revision']},headers=h).status_code==409
    seen=[]
    def fake(code,content,language,tests):
        seen.append(tests)
        return [dict(passed=True,status='Accepted',output='SECRET hidden output',error='SECRET',duration_ms=1) for _ in tests]
    monkeypatch.setattr(module,'runner',fake)
    assert client.post(f'{BASE}/questions/{qid}/validate',json={'revision':a['revision']},headers=h).json['passed']
    assert client.post(f'{BASE}/questions/{qid}/publish',json={'revision':a['revision']},headers=h).json['admin_only']
    data=client.post(f'{BASE}/questions/{qid}/execute',json={'revision':a['revision'],'code':'print(5)','action':'submit'},headers=h).json
    hidden=data['results'][1]
    assert hidden['hidden'] and 'output' not in hidden and 'expected' not in hidden and 'error' not in hidden and 'input' not in hidden
    c=deepcopy(a['content']);c['statement']='Changed question'
    edited=client.put(f'{BASE}/questions/{qid}',json={'revision':a['revision'],'content':c},headers=h)
    assert edited.status_code==200 and not edited.json['validated'] and edited.json['status']=='DRAFT'
    assert client.post(f'{BASE}/questions/{qid}/execute',json={'revision':a['revision'],'code':'print(5)','action':'run'},headers=h).status_code==409

def test_invalid_fixtures_and_categories(client):
    h,b=setup(client)
    for path in ('../escape','/etc/passwd','a/../../x','main.py'):
        c=deepcopy(b);c['questions'][0]['content']['tests'][0]['files']={path:'bad'}
        assert client.post(BASE+'/import',json={'bundle':c,'save':True},headers=h).status_code==400
    c=deepcopy(b);c['questions'][0]['content']['tests'][1]['hidden']=False
    assert client.post(BASE+'/import',json={'bundle':c},headers=h).status_code==200
    assert client.post(BASE+'/courses',json={'slug':'c','name':'C','language':'unsupported'},headers=h).status_code==400

def test_all_course_templates_have_valid_original_examples(client):
    h,b=setup(client)
    for slug in ('python','pdsa','java','dbms','sc'):
        bundle=client.get(BASE+'/template?course_slug='+slug).json
        assert bundle['course_slug']==slug and len(bundle['questions'])==1
        assert client.post(BASE+'/import',json={'bundle':bundle},headers=h).status_code==200
    sql=client.get(BASE+'/template?course_slug=dbms').json['questions'][0]['content']
    assert sql['tests'][1]['setup_sql'] and sql['tests'][0]['expected']!=sql['tests'][1]['expected']

def test_runner_http_failure_and_prefix_are_handled(client,app,monkeypatch):
    import backend.oppe as m
    app.config.update(OPPE_RUNNER_URL='https://runner.example.test',OPPE_RUNNER_TOKEN='x'*40)
    h,b=setup(client);content=b['questions'][0]['content'];content.update(prefix='# fixed prefix\n',suffix='\n# fixed suffix')
    qid,a=create(client,h,b)
    calls=[]
    class Response:
        status_code=200
        def json(self):return {'results':[{'passed':True,'status':'Accepted','output':'5','error':''}]}
    def post(url,**kw):calls.append(kw);return Response()
    monkeypatch.setattr(m.requests,'post',post)
    r=client.post(f'{BASE}/questions/{qid}/execute',json={'revision':a['revision'],'code':'print(5)','action':'run'},headers=h)
    assert r.status_code==200
    assert calls[0]['json']['code']=='# fixed prefix\nprint(5)\n# fixed suffix'
    assert calls[0]['allow_redirects'] is False
    monkeypatch.setattr(Response,'json',lambda self:{'results':[]})
    assert client.post(f'{BASE}/questions/{qid}/execute',json={'revision':a['revision'],'code':'print(5)','action':'run'},headers=h).status_code==503

def test_owner_bundles_are_valid_private_drafts(client):
    import json
    from pathlib import Path
    from backend.oppe import checked_content,OPPECourse
    setup(client)
    root=Path(__file__).resolve().parents[1]
    bundles=json.loads((root/'backend/data/oppe/seed-bundles-20261020.json').read_text())
    assert sum(len(b['questions']) for b in bundles)==278
    for bundle in bundles:
        c=OPPECourse.query.filter_by(slug=bundle['course_slug']).one()
        for row in bundle['questions']:
            content=checked_content(row['content'],c)
            assert not any(t['hidden'] for t in content['tests'])
            assert 'data:image/' not in content['statement']

def test_diagrams_remain_admin_only(client):
    from pathlib import Path
    image=next((Path(__file__).resolve().parents[1]/'backend/data/oppe/images').glob('*.png'))
    url=BASE+'/assets/'+image.name
    assert client.get(url).status_code==401
    setup(client)
    r=client.get(url)
    assert r.status_code==200
    assert r.mimetype=='image/png'
    assert r.headers['Cache-Control']=='no-store'
    assert client.get(BASE+'/assets/not-an-image.png').status_code==404


def test_every_seeded_owner_question_opens_without_reimport(client):
    import json
    from pathlib import Path
    from backend.oppe import OPPECourse
    setup(client)
    bundles=json.loads((Path(__file__).resolve().parents[1]/'backend/data/oppe/seed-bundles-20261020.json').read_text())
    for bundle in bundles:
        course=OPPECourse.query.filter_by(slug=bundle['course_slug']).one()
        for entry in bundle['questions']:
            # Exactly how the migration stores content: derived format can be absent.
            content=deepcopy(entry['content']);content.pop('format',None)
            q=OPPEQuestion(course_id=course.id,external_id=entry['external_id'],content=content)
            db.session.add(q);db.session.flush()
            response=client.get(BASE+'/questions/'+str(q.id))
            assert response.status_code==200,(entry['external_id'],response.data)
            assert response.json['question']['format']=='program'
            assert 'reference_solution' not in response.json['question']
    db.session.rollback()
