import gzip, json, re
import pytest
from fakeredis import FakeRedis
from backend.models import db, Question, QuestionImage, PaperProgress, Attempt
from backend.content_cache import cached
from backend.storage import configure_delivery, ensure_local, local_path
from test_production_stability import seed
from conftest import login


@pytest.fixture
def redis_cache(app):
    r=FakeRedis(decode_responses=True)
    app.config['CONTENT_CACHE_URL']='redis://test.invalid/0'
    app.extensions['content_redis']=r
    return r


def test_cache_hits_invalidation_rollback_and_no_personal_state(app,client,redis_cache):
    pid=seed(1)[0]
    first=client.get('/api/catalog');second=client.get('/api/catalog')
    assert first.json==second.json and 'queries;desc="0"' in second.headers['Server-Timing']
    client.get(f'/api/papers/{pid}/questions')
    q=Question.query.first();q.text='Changed';db.session.commit()
    assert 'Changed' in [x['text'] for x in client.get(f'/api/papers/{pid}/questions').json['items']]
    q.text='Rolled back';db.session.flush();db.session.rollback()
    assert 'Rolled back' not in [x['text'] for x in client.get(f'/api/papers/{pid}/questions').json['items']]
    h=login(client)
    a=client.post('/api/attempts?bootstrap=1',headers=h,json={'paper_id':pid,'mode':'exam'}).json
    assert len(a['items'])==2
    for item in a['items']:
        assert 'feedback' not in item
        assert 'answers' not in item['question']
        assert '_asset_path' not in json.dumps(item)
    client.get(f'/api/papers/{pid}')
    with client.session_transaction() as sess:uid=sess['uid']
    db.session.add(PaperProgress(user_id=uid,paper_id=pid,last_score=80,last_attempted_at=1));db.session.commit()
    assert client.get(f'/api/papers/{pid}').json['progress']['last_score']==80
    assert app.test_client().get(f'/api/papers/{pid}').json['progress'] is None
    assert not any('attempt' in k or 'progress' in k for k in redis_cache.scan_iter())


def test_cache_failure_and_loader_error_do_not_double_run(app,redis_cache,monkeypatch):
    calls=[]
    def fail():calls.append(1);raise ValueError('loader failed')
    with pytest.raises(ValueError):cached('bad',fail)
    assert calls==[1]
    monkeypatch.setattr(redis_cache,'get',lambda *a:(_ for _ in ()).throw(ConnectionError()))
    assert cached('offline',lambda:42)==42


def test_image_cache_hit_never_downloads(app,client,monkeypatch):
    seed(1);image=QuestionImage.query.first();path=local_path(image.path)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'PNG')
    monkeypatch.setattr('backend.storage.remote_bytes',lambda name:pytest.fail('R2 on local hit'))
    login(client);r=client.get(f'/api/images/{image.id}')
    assert r.status_code==200
    assert 'asset_hit;desc="1"' in r.headers['Server-Timing']
    assert 'ensure_local;dur=' in r.headers['Server-Timing']


def test_attempt_bootstrap_signed_urls_cover_attempt_lifetime(app,client,monkeypatch):
    pid=seed(1)[0];h=login(client)
    app.config.update(STORAGE_BACKEND='r2',IMAGE_DELIVERY='signed',R2_ENDPOINT_URL='https://test.r2.cloudflarestorage.com')
    configure_delivery(app)
    expiries=[]
    monkeypatch.setattr('backend.storage.private_asset_url',lambda path,id,expires=600:(expiries.append(expires) or 'https://test.r2.cloudflarestorage.com/bucket/'+path))
    a=client.post('/api/attempts?bootstrap=1',headers=h,json={'paper_id':pid,'mode':'exam','duration_seconds':5400}).json
    assert expiries and min(expiries)>5400
    assert all(img['url'].startswith('https://test.r2.cloudflarestorage.com/') for item in a['items'] for img in item['question']['images'])


def test_signed_delivery_no_download_and_csp(app,client,monkeypatch):
    seed(1);login(client)
    app.config.update(STORAGE_BACKEND='r2',IMAGE_DELIVERY='signed',R2_ENDPOINT_URL='https://test.r2.cloudflarestorage.com')
    configure_delivery(app)
    monkeypatch.setattr('backend.storage.private_asset_url',lambda path,id,expires=600:'https://test.r2.cloudflarestorage.com/bucket/'+path+'?signed=1')
    monkeypatch.setattr('backend.storage.ensure_local',lambda name:pytest.fail('No disk for direct images'))
    r=client.get('/api/papers/1/questions')
    assert r.json['items'][0]['images'][0]['url'].startswith('https://test.r2.cloudflarestorage.com/')
    assert 'img-src' in r.headers['Content-Security-Policy']
    assert 'https://test.r2.cloudflarestorage.com' in r.headers['Content-Security-Policy']
    image=QuestionImage.query.first()
    r=client.get(f'/api/images/{image.id}')
    assert r.status_code==302 and r.headers['Cache-Control']=='private, max-age=300'
    assert app.test_client().get(f'/api/images/{image.id}').status_code==401


def test_cdn_explicit_allowlist_only(app,client,tmp_path):
    seed(1);manifest=tmp_path/'images.json'
    manifest.write_text(json.dumps({'formula.png':'public-questions/'+'a'*64+'.png'}))
    app.config.update(STORAGE_BACKEND='r2',IMAGE_DELIVERY='cdn',IMAGE_CDN_BASE_URL='https://img.example.test',IMAGE_CDN_MANIFEST=str(manifest))
    configure_delivery(app)
    r=client.get('/api/papers/1/questions')
    assert r.json['items'][0]['images'][0]['url']=='https://img.example.test/public-questions/'+'a'*64+'.png'
    manifest.write_text(json.dumps({'formula.png':'source.pdf'}))
    with pytest.raises(ValueError):configure_delivery(app)


def test_response_save_queries_and_bootstrap_privacy(app,client):
    pid=seed(1)[0];h=login(client)
    a=client.post('/api/attempts?bootstrap=1',json={'paper_id':pid,'mode':'exam'},headers=h).json
    status=client.get(f"/api/attempts/{a['id']}/status")
    assert status.status_code==200 and 'palette' not in status.json and 'items' not in status.json
    status_count=int(re.search(r'queries;desc="(\\d+)"',status.headers['Server-Timing'])[1])
    assert status_count<=2  # authenticated user + owned attempt; no AttemptAnswer snapshot load.
    qids=[p['question_id'] for p in a['palette'][:2]]
    r=client.post(f"/api/attempts/{a['id']}/answers",json={'items':[{'question_id':qids[0],'answer':['b']},{'question_id':qids[1],'marked':True}]},headers=h)
    assert r.status_code==200 and len(r.json['items'])==2 and all('feedback' not in item for item in r.json['items'])
    count=int(re.search(r'queries;desc="(\\d+)"',r.headers['Server-Timing'])[1])
    assert count<=5  # one auth read + one batched owned-answer read + one transaction.
    r=client.get(f"/api/attempts/{a['id']}?bootstrap=1")
    assert r.json['items'][0]['answer']==['b'] and r.json['items'][1]['marked'] is True and 'feedback' not in r.json['items'][0]
    # Legacy single-response clients remain supported.
    single=client.post(f"/api/attempts/{a['id']}/answers",json={'question_id':qids[0],'answer':None},headers=h)
    assert single.status_code==200 and single.json['state']=='NOT_ANSWERED'

def test_public_gzip_excludes_session(app,client):
    seed(12)
    r=client.get('/api/catalog',headers={'Accept-Encoding':'gzip'})
    assert r.headers['Content-Encoding']=='gzip'
    assert json.loads(gzip.decompress(r.data))['courses']
    assert 'Content-Encoding' not in client.get('/api/session',headers={'Accept-Encoding':'gzip'}).headers
