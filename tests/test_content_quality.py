from backend.models import db,Course,QuestionImage,ContentQualityReview,StudyPaperSettings,CourseGuide
from backend.content_quality import fingerprint
from backend.public_content import content_parts
from test_study_pages import seed
from conftest import login

def test_public_image_order_table_and_missing_marker(client):
    c,p,q,s=seed()
    q.text='Before [[IMAGE:diagram]] After [[IMAGE:missing]]\n| Name | Value |\n| --- | --- |\n| A | 2 |\n'
    db.session.add(QuestionImage(question_id=q.id,path='diagram.png',alt='Diagram'));db.session.commit()
    r=client.get(f'/study/papers/{p.id}')
    assert r.status_code==200
    assert '[[IMAGE:' not in r.text
    assert r.text.index('Before')<r.text.index('alt="Diagram"')<r.text.index('After')
    assert '<table>' in r.text and '<th scope="col" class="math-copy">Name</th>' in r.text
    assert 'Source diagram or notation unavailable' in r.text
    assert r.text.count('alt="Diagram"')==1

def test_quality_is_private_non_destructive_and_versioned(client):
    c,p,q,s=seed();q.text='Section Id: 123\nWhat is the answer?';db.session.commit()
    assert client.get('/api/admin/content-quality/scan').status_code==401
    h=login(client,True)
    r=client.get('/api/admin/content-quality/scan').json
    assert r['scanned']==2
    row=next(i for i in r['items'] if i['id']==q.id)
    assert 'Internal exam metadata in question' in row['flags']
    assert q.status=='AVAILABLE'
    d=client.get(f'/api/admin/content-quality/questions/{q.id}').json
    path=f'/api/admin/content-quality/questions/{q.id}/review'
    assert client.post(path,json={'fingerprint':d['fingerprint'],'checks':{}},headers=h).status_code==400
    checks={k:True for k in ('source','calculation','options','formatting')}
    assert client.post(path,json={'fingerprint':d['fingerprint'],'checks':checks},headers=h).status_code==200
    s.text='New explanation';db.session.commit()
    assert db.session.get(ContentQualityReview,q.id).fingerprint!=fingerprint(q,s)
    assert client.post(path,json={'fingerprint':d['fingerprint'],'checks':checks},headers=h).status_code==409

def test_course_guide_and_featured_guard(client):
    c,p,q,s=seed();c.name='Machine Learning Foundations';db.session.commit()
    r=client.get(f'/study/courses/{c.id}')
    assert 'Vectors and matrices' in r.text and 'Common mistakes' in r.text
    h=login(client,True)
    d=client.get(f'/api/admin/content-quality/courses/{c.id}').json['guide']
    d['published']=True;d['introduction']='A course guide <script>not executable</script>'
    assert client.put(f'/api/admin/content-quality/courses/{c.id}',json=d,headers=h).status_code==200
    text=client.get(f'/study/courses/{c.id}').text
    assert '&lt;script&gt;' in text and '<script>not executable' not in text
    assert client.put(f'/api/admin/content-quality/papers/{p.id}',json={'featured':True,'allow_ads':False},headers=h).status_code==200
    assert client.get('/api/study-featured').json['items'][0]['id']==p.id
    s.version='outdated';db.session.commit()
    assert client.get('/api/study-featured').json['items']==[]
    assert client.get('/api/admin/content-quality/deployment').json['commit']=='local'

def test_ads_fail_closed_and_excluded_from_exam(app,client):
    c,p,q,s=seed();s.final_answer='4';q.answers='4';q.answer_status='ANSWER_AVAILABLE';s.version=__import__('backend.ai_solutions',fromlist=['version']).version(__import__('backend.engine',fromlist=['question_snapshot']).question_snapshot(q))
    db.session.add(StudyPaperSettings(paper_id=p.id,allow_ads=True,featured=True))
    db.session.add(ContentQualityReview(question_id=q.id,fingerprint=fingerprint(q,s),checks={'source':True,'calculation':True,'options':True,'formatting':True}))
    db.session.commit()
    app.config.update(STUDY_ADS_ENABLED='true',ADSENSE_CMP_READY='false',ADSENSE_PUBLISHER_ID='pub-1234567890123456',ADSENSE_STUDY_SLOT='1234567890')
    assert '/study-ads.js' not in client.get(f'/study/papers/{p.id}').text
    app.config['ADSENSE_CMP_READY']='true'
    response=client.get(f'/study/papers/{p.id}')
    assert '/study-ads.js' in response.text
    assert 'pagead2.googlesyndication.com' in response.headers['Content-Security-Policy']
    # No global loader, even when site ads are enabled.
    for path in ('/','/contact','/study','/admin','/paper/1'):
        r=client.get(path)
        assert '/study-ads.js' not in r.text
        assert 'pagead2.googlesyndication.com' not in r.headers['Content-Security-Policy']
