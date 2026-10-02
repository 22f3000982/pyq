import io,hashlib
import fitz,pytest
from backend.models import db,Question,QuestionImage,QuestionReview,ContentReport,IngestionFile,IngestionBatch,Paper
from backend.engine import question_snapshot
from backend.ingestion import process_file
from conftest import login
from test_engine import seed


def pdf_bytes():
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((40,50),'Question 1. A replacement PDF')
        return doc.tobytes()


def setup(client):
    p=seed();q=Question.query.filter_by(paper_id=p.id).first();h=login(client,True)
    return p,q,h


def edit(client,q,h,**fields):
    version=client.get(f'/api/admin/questions/{q.id}').json['updated_at']
    return client.patch(f'/api/admin/questions/{q.id}',headers=h,json={'updated_at':version,**fields})


def test_edit_report_resolution_history_undo_and_snapshot(app,client):
    p=seed();q=Question.query.filter_by(paper_id=p.id).first();vh=login(client)
    attempt=client.post('/api/attempts',headers=vh,json={'paper_id':p.id,'mode':'exam'}).json
    rid=client.post(f'/api/questions/{q.id}/report-format',headers=vh,json={'issue':'TEXT'}).json['id']
    h=login(client,True);old=q.text;oldversion=q.updated_at
    r=edit(client,q,h,text='Corrected stem',passage='Shared setup',marks=5,resolve_report_id=rid)
    assert r.status_code==200,r.json
    assert q.text=='Corrected stem' and question_snapshot(q)['passage']=='Shared setup'
    assert q.evidence['_admin_locked'] and db.session.get(ContentReport,rid).status=='RESOLVED'
    assert QuestionReview.query.count()==1
    stored=client.get(f"/api/attempts/{attempt['id']}/questions/{q.id}").json
    assert stored['question']['text']==old and stored['question']['marks']==4
    assert client.patch(f'/api/admin/questions/{q.id}',headers=h,json={'updated_at':oldversion,'text':'Stale'}).status_code==409
    r=client.post(f'/api/admin/questions/{q.id}/undo',headers=h,json={'updated_at':q.updated_at})
    assert r.status_code==200 and q.text==old and q.marks==4
    assert q.evidence['_admin_locked'] and QuestionReview.query.count()==2


def test_hide_restore_counts_new_attempts_and_admin_only(app,client):
    p,q,h=setup(client)
    before=client.get(f'/api/papers/{p.id}').json['question_count']
    r=client.post(f'/api/admin/questions/{q.id}/visibility',headers=h,json={'updated_at':q.updated_at,'hidden':True})
    assert r.status_code==200 and q.status=='HIDDEN'
    assert client.get(f'/api/papers/{p.id}').json['question_count']==before-1
    assert client.get('/api/admin/questions?status=HIDDEN').json['total']==1
    a=client.post('/api/attempts',headers=h,json={'paper_id':p.id,'mode':'practice'}).json
    assert q.id not in [i['question_id'] for i in a['palette']]
    assert client.post(f'/api/admin/questions/{q.id}/visibility',headers=h,json={'updated_at':q.updated_at,'hidden':False}).status_code==200
    assert q.status=='AVAILABLE'
    guest=app.test_client();gh=login(guest)
    assert guest.get(f'/api/admin/questions/{q.id}').status_code==401
    assert guest.patch(f'/api/admin/questions/{q.id}',headers=gh,json={'updated_at':q.updated_at,'text':'bad'}).status_code==401
    assert client.patch(f'/api/admin/questions/{q.id}',json={'text':'bad'}).status_code==403


@pytest.mark.parametrize('fields',[{'text':''},{'options':[{'key':'A','text':'a'}]},{'answers':['Z']},{'marks':-1},{'marks':'five'},{'options':[{'key':'A','text':'a'},{'key':'A','text':'b'}]},{'image_ids':[999]},{'kind':'BAD'}])
def test_invalid_edits_atomic(app,client,fields):
    p,q,h=setup(client);old=q.text
    r=edit(client,q,h,**fields)
    assert r.status_code==400,r.json
    db.session.refresh(q);assert q.text==old and QuestionReview.query.count()==0


def test_image_upload_selection_undo_preserves_asset_ids(app,client):
    p,q,h=setup(client);pix=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,2,2));pix.clear_with(255)
    r=client.post(f'/api/admin/questions/{q.id}/images',headers=h,data={'updated_at':str(q.updated_at),'file':(io.BytesIO(pix.tobytes('png')),'diagram.png')})
    assert r.status_code==201,r.json
    image_id=r.json['question']['images'][0]['id'];assert client.get(f'/api/images/{image_id}').status_code==200
    assert edit(client,q,h,image_ids=[]).status_code==200
    assert question_snapshot(q)['images']==[] and db.session.get(QuestionImage,image_id) is not None
    assert client.post(f'/api/admin/questions/{q.id}/undo',headers=h,json={'updated_at':q.updated_at}).status_code==200
    assert question_snapshot(q)['images'][0]['id']==image_id


def record(number,status='AVAILABLE'):
    return {'number':str(number),'kind':'MCQ','text':'New text '+str(number),'options':[{'key':'A','text':'A'},{'key':'B','text':'B'}],'answers':['A'],'marks':4,'negative_marks':1,'status':status,'source_pages':[1]}


def mocked_parser(monkeypatch,records):
    monkeypatch.setattr('backend.ingestion.layout_document',lambda *a,**kw:{'text':'Readable question text','pages':[],'assets':[],'warnings':[]})
    monkeypatch.setattr('backend.ingestion.parse_document',lambda layout:(records,{},[]))


def test_replacement_failure_preserves_bank_and_success_keeps_overrides(app,client,monkeypatch):
    p,q,h=setup(client);old=q.text;data=pdf_bytes()
    invalid=client.post(f'/api/admin/papers/{p.id}/replacement',headers=h,data={'file':(io.BytesIO(b'bad'),'bad.pdf')})
    assert invalid.status_code==400 and IngestionFile.query.count()==0
    assert edit(client,q,h,text='Manually corrected').status_code==200
    hidden=Question.query.filter_by(paper_id=p.id,number='2').one()
    assert client.post(f'/api/admin/questions/{hidden.id}/visibility',headers=h,json={'updated_at':hidden.updated_at,'hidden':True}).status_code==200
    r=client.post(f'/api/admin/papers/{p.id}/replacement',headers=h,data={'file':(io.BytesIO(data),'new.pdf')});assert r.status_code==202,r.json
    fid=r.json['file']['id'];count=Question.query.filter_by(paper_id=p.id,status='AVAILABLE').count()
    assert edit(client,q,h,text='Concurrent edit').status_code==409
    mocked_parser(monkeypatch,[record(1,'EXTRACTION_FAILED')])
    r=client.post(f'/api/admin/ingestion/{fid}/process-now',headers=h,json={})
    assert r.status_code==200 and r.json['file']['status']=='EXTRACTION_FAILED'
    assert Question.query.filter_by(paper_id=p.id,status='AVAILABLE').count()==count and q.text=='Manually corrected'
    assert client.post(f'/api/admin/ingestion/{fid}/process-now',headers=h,json={}).status_code==409
    # Uploading identical bytes creates one targeted job without requeuing the previous one.
    r=client.post(f'/api/admin/papers/{p.id}/replacement',headers=h,data={'file':(io.BytesIO(data),'new.pdf')});fid2=r.json['file']['id']
    assert fid2!=fid and db.session.get(IngestionFile,fid).status=='EXTRACTION_FAILED'
    mocked_parser(monkeypatch,[record(1),record(2),record(3)])
    r=client.post(f'/api/admin/ingestion/{fid2}/process-now',headers=h,json={});assert r.status_code==200,r.json
    db.session.refresh(q);db.session.refresh(hidden)
    assert q.text=='Manually corrected' and hidden.status=='HIDDEN'
    assert len(Question.query.filter_by(paper_id=p.id,number='1').all())==1
    assert client.get(f'/api/admin/ingestion/{fid2}/pages/1').status_code==200


def test_partial_replacement_does_not_replace_valid_bank(app,client,monkeypatch):
    p,q,h=setup(client);before=[(x.id,x.text,x.status) for x in Question.query.filter_by(paper_id=p.id).all()]
    r=client.post(f'/api/admin/papers/{p.id}/replacement',headers=h,data={'file':(io.BytesIO(pdf_bytes()),'partial.pdf')});fid=r.json['file']['id']
    mocked_parser(monkeypatch,[record(1),record(2,'EXTRACTION_FAILED')])
    client.post(f'/api/admin/ingestion/{fid}/process-now',headers=h,json={})
    assert [(x.id,x.text,x.status) for x in Question.query.filter_by(paper_id=p.id).all()]==before
    assert db.session.get(IngestionFile,fid).status=='EXTRACTION_FAILED'
