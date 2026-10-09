from backend.models import db,ContentReport,Question
from test_engine import seed
from conftest import login


def test_guest_report_dedup_and_admin_review(app,client):
    p=seed();q=Question.query.filter_by(paper_id=p.id).first();h=login(client)
    url=f'/api/questions/{q.id}/report-format'
    assert client.post(url,json={'issue':'IMAGE'}).status_code==403
    r=client.post(url,headers=h,json={'issue':'FORMULA','description':' Equation is clipped '})
    assert r.status_code==201 and not r.json['duplicate']
    rid=r.json['id'];assert ContentReport.query.count()==1
    assert client.post(url,headers=h,json={'issue':'TEXT'}).json['duplicate']
    assert ContentReport.query.count()==1
    assert client.get('/api/admin/content-reports').status_code==401
    assert client.patch(f'/api/admin/content-reports/{rid}',headers=h,json={'status':'RESOLVED'}).status_code==401
    ah=login(client,True)
    rows=client.get('/api/admin/content-reports').json
    assert rows['total']==1 and rows['items'][0]['description']=='Equation is clipped'
    assert 'guest_hash' not in rows['items'][0]
    detail=client.get(f'/api/admin/content-reports/{rid}').json
    assert detail['question']['id']==q.id and detail['paper_id']==p.id
    assert client.patch(f'/api/admin/content-reports/{rid}',headers=ah,json={'status':'RESOLVED'}).json['resolved_at']
    assert client.get('/api/admin/content-reports').json['total']==0
    assert client.get('/api/admin/content-reports?status=RESOLVED').json['total']==1
    assert client.patch(f'/api/admin/content-reports/{rid}',headers=ah,json={'status':'OPEN'}).json['resolved_at'] is None


def test_report_validation_visibility_and_guest_quota(app,client):
    p=seed();qs=Question.query.filter_by(paper_id=p.id).all();h=login(client)
    url=f'/api/questions/{qs[0].id}/report-format'
    for payload in [{'issue':'KEY'},{'issue':[]},{'issue':'TEXT','description':'x'*1001},{'issue':'TEXT','description':{}}]:
        assert client.post(url,headers=h,json=payload).status_code==400
    assert client.post('/api/questions/999999/report-format',headers=h,json={'issue':'TEXT'}).status_code==404
    qs[0].status='EXTRACTED';db.session.commit()
    assert client.post(url,headers=h,json={'issue':'TEXT'}).status_code==404
    p.status='ARCHIVED';db.session.commit()
    assert client.post(f'/api/questions/{qs[1].id}/report-format',headers=h,json={'issue':'TEXT'}).status_code==404
    p.status='AVAILABLE';db.session.commit()
    assert client.post(f'/api/questions/{qs[1].id}/report-format',headers=h,json={'issue':'TEXT'}).status_code==201
    guest=ContentReport.query.first().guest_hash
    for n in range(19):
        q=Question(paper_id=p.id,number=str(n+20),kind='MCQ',text='Q',status='AVAILABLE');db.session.add(q);db.session.flush();db.session.add(ContentReport(question_id=q.id,guest_hash=guest,issue='TEXT'))
    db.session.commit()
    assert client.post(f'/api/questions/{qs[2].id}/report-format',headers=h,json={'issue':'TEXT'}).status_code==429
    other=app.test_client();oh=login(other)
    assert other.post(f'/api/questions/{qs[1].id}/report-format',headers=oh,json={'issue':'TEXT'}).status_code==201


def test_reports_removed_before_library_reset(app,client):
    p=seed();q=Question.query.filter_by(paper_id=p.id).first();h=login(client)
    assert client.post(f'/api/questions/{q.id}/report-format',headers=h,json={'issue':'TEXT'}).status_code==201
    from backend.library_campaign import library_inventory,reset_library
    assert library_inventory(False)['counts']['content_reports']==1
    # Existing reset API performs dependency-ordered deletion of this new table.
    ah=login(client,True)
    r=client.post('/api/admin/library-reset',headers=ah,json={'confirmation':'RESET PYQ LIBRARY','cleanup_storage':False})
    assert r.status_code==200,r.json
    assert ContentReport.query.count()==Question.query.count()==0
