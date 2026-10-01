import io,fitz,pytest,json
from pathlib import Path
from werkzeug.datastructures import FileStorage
from backend.models import *
from backend.ingestion import store_upload,work_once,process_file
from backend.visual_pdf import layout_document
from backend.automatic_parser import parse_document
from backend.numeric import parse_numeric_key,numeric_correct
from backend.acquisition import safe_url,download_url
from conftest import login
from test_engine import seed
REAL=Path(__file__).resolve().parents[1]/'sample-data/software-testing-may-2026-quiz1.pdf'

def ingest_real(app):
    p=seed()
    for q in Question.query.all():db.session.delete(q)
    p.duration_seconds=None;db.session.commit()
    batch=IngestionBatch(user_id=User.query.filter_by(role='ADMIN').first().id);db.session.add(batch);db.session.commit()
    with open(REAL,'rb') as stream:f=store_upload(FileStorage(stream=stream,filename='real.pdf',content_type='application/pdf'),p,batch)
    assert work_once();return p,f

def test_real_automatic_pipeline_to_student_result(app,client):
    p,f=ingest_real(app)
    assert f.status=='AVAILABLE',f.error
    assert Question.query.filter_by(status='AVAILABLE').count()==20
    assert Question.query.filter_by(status='INSTRUCTION').count()==1
    assert p.source_metadata['declared_total_questions']==17
    assert p.source_metadata['declared_total_marks']==100
    assert p.source_metadata['extracted_records']==21
    assert p.source_metadata['discrepancies']
    h=login(client)
    landing=client.get(f'/api/papers/{p.id}').json
    assert landing['question_count']==20 and landing['total_marks']==100
    assert landing['duration_seconds'] is None
    a=client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam','duration_seconds':1800},headers=h).json
    assert 'timed practice' in a['title'];aid=a['id'];qid=a['palette'][0]['question_id']
    question=client.get(f'/api/attempts/{aid}/questions/{qid}').json
    assert 'answers' not in question['question'] and 'evidence' not in question['question'] and 'feedback' not in question
    q=Question.query.filter_by(number='2').one();assert q.answers==['6406537043124'];assert q.marks==5 and q.negative_marks==0
    response=client.post(f'/api/attempts/{aid}/answers',json={'question_id':q.id,'answer':q.answers,'marked':True},headers=h)
    assert 'feedback' not in response.json
    result=client.post(f'/api/attempts/{aid}/submit',headers=h).json['result']
    assert result['score']==5 and result['total_marks']==100
    assert client.get(f'/api/attempts/{aid}/review').json['items'][0]['question']['answers']==q.answers
    assert client.get('/api/attempts').json['total']==0
    assert client.get('/api/progress').json['total']==0
    assert QuestionImage.query.count()>0
    assert all('pdf' not in img.path for img in QuestionImage.query.all())
    # No approval endpoints remain.
    ah=login(app.test_client(),True)
    assert client.post(f'/api/admin/questions/{q.id}/publish',headers=h).status_code in (404,405)

def test_duplicate_upload_and_reprocessing(app):
    p,f=ingest_real(app);count=Question.query.count();images=QuestionImage.query.count()
    process_file(f.id)
    assert Question.query.count()==count and QuestionImage.query.count()==images
    batch=db.session.get(IngestionBatch,f.batch_id)
    with open(REAL,'rb') as stream:duplicate=store_upload(FileStorage(stream=stream,filename='same.pdf',content_type='application/pdf'),p,batch)
    assert duplicate.status=='DUPLICATE' and Question.query.count()==count

@pytest.mark.parametrize('raw,response,correct',[('42','42',True),('-3.5','-3.5',True),('1/3','1/3',True),('4 to 6','5',True),('4 to 6','7',False),('2, 4, 8','4',True),('-2 to -1','-1.5',True)])
def test_exact_numeric_keys(raw,response,correct):assert numeric_correct(response,parse_numeric_key(raw))==correct

def test_source_hosts_restricted():
    for url in ['http://localhost/a','http://127.0.0.1/x','https://example.com/x','file:///etc/passwd']:
        with pytest.raises(ValueError):safe_url(url)
    assert download_url('https://drive.google.com/file/d/abc_123/view').endswith('id=abc_123')

def test_green_and_red_visual_evidence(app,tmp_path):
    with fitz.open(REAL) as doc:layout=layout_document(doc,tmp_path,'sample')
    q,_,_=parse_document(layout)
    key=q[1]['evidence']['answer_indicators']
    assert any(e['kind']=='green' for e in key['6406537043124'])
    assert any(e['method']=='embedded_indicator_pixels' for e in key['6406537043124'])
    assert any(e['kind']=='red' for e in key['6406537043122'])
    assert q[1]['answers']==['6406537043124']
    assert len(q[14]['images'])>=4 # image options and source formulae
    assert len(q[17]['images'])>=1 # shared graph attached to cross-page child

def test_failed_file_does_not_stop_next(app):
    p=seed();batch=IngestionBatch(user_id=User.query.first().id);db.session.add(batch);db.session.commit()
    bad=store_upload(FileStorage(stream=io.BytesIO(b'broken'),filename='bad.pdf',content_type='application/pdf'),p,batch)
    assert bad.status=='PROCESSING_FAILED'
    with open(REAL,'rb') as stream:good=store_upload(FileStorage(stream=stream,filename='real.pdf',content_type='application/pdf'),p,batch)
    work_once();assert good.status=='AVAILABLE';assert db.session.get(Paper,p.id)

def test_pixel_color_even_when_text_has_no_color(app,tmp_path):
    doc=fitz.open();page=doc.new_page();page.insert_text((50,50),'Question Number : 1 Question Id : 123456789 Question Type : MCQ\nCorrect Marks : 2\nQuestion Label : Multiple Choice Question\nDEMO DATA: choose a letter.\nOptions :\n12345671.  Alpha\n12345672.  Beta')
    for b in page.get_text('dict')['blocks']:
        for line in b.get('lines',[]):
            for span in line['spans']:
                if span['text'].startswith('12345671.'):
                    # A green background highlight exists only in rendering, not text colour.
                    bbox=fitz.Rect(span['bbox']);page.draw_rect(bbox,color=None,fill=(0,.8,0),overlay=False)
    layout=layout_document(doc,tmp_path,'pixel');questions,_,_=parse_document(layout)
    assert questions[0]['answers']==['12345671']
    assert all(e['method']!='pdf_text_color' for e in questions[0]['evidence']['answer_indicators']['12345671'])

def test_red_only_never_guesses_remaining_option(app,tmp_path):
    with fitz.open(REAL) as doc:layout=layout_document(doc,tmp_path,'red')
    for indicators in layout['indicators'].values():indicators[:]=[e for e in indicators if e['kind']=='red']
    questions,_,_=parse_document(layout)
    assert questions[1]['answers'] is None

def test_timeout_without_browser(app,client):
    import time
    p=seed();h=login(client);a=client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam'},headers=h).json
    attempt=db.session.get(Attempt,a['id']);attempt.deadline=time.time()-1;db.session.commit();work_once()
    assert db.session.get(Attempt,a['id']).status=='SUBMITTED'

def test_auth_admin_and_bad_pdf(client,app):
    p=seed();h=login(client)
    assert client.get('/api/admin/stats').status_code==401
    assert client.post('/api/admin/process-catalog',json={},headers=h).status_code==401
    from backend.ingestion import validate_pdf
    with pytest.raises(ValueError):validate_pdf(b'not a PDF')
