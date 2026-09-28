"""Five actual PDFs pass through the same HTTP upload route used by the form."""
import json
from pathlib import Path
import pytest
from conftest import login
from test_engine import seed
from backend.models import db,Question,IngestionFile,Paper
from backend.ingestion import work_once
ROOT=Path(__file__).resolve().parents[1]
FILES=json.loads((ROOT/'sample-data/five-papers.json').read_text())
@pytest.mark.parametrize('source,expected,marks',[(FILES[0],20,50),(FILES[1],27,100),(FILES[2],16,25),(FILES[3],22,25),(FILES[4],26,25)])
def test_real_pdf_upload_creates_usable_paper(app,client,source,expected,marks):
    p=seed();h=login(client,True)
    metadata={'course_id':str(p.course_id),'term_id':str(p.term_id),'exam_type_id':str(p.exam_type_id),'name':'Real source upload test'}
    with open(ROOT/source['file'],'rb') as f:
        r=client.post('/api/admin/upload-pyq',data={**metadata,'file':(f,Path(source['file']).name)},headers=h)
    assert r.status_code==202,r.json
    fid=r.json['file']['id'];pid=r.json['paper']['id'];assert r.json['file']['status']=='QUEUED'
    assert work_once()
    status=client.get(f'/api/admin/ingestion/{fid}').json
    assert status['file']['effective_status']=='AVAILABLE',status
    assert status['paper']['question_count']==expected and status['paper']['total_marks']==marks
    qs=Question.query.filter_by(paper_id=pid,status='AVAILABLE').all()
    assert all(q.answers is not None for q in qs)
    assert any(e['stage']=='AUTOMATIC_VALIDATION' for e in status['file']['events'])
    count=Question.query.count()
    with open(ROOT/source['file'],'rb') as f:
        again=client.post('/api/admin/upload-pyq',data={**metadata,'file':(f,'again.pdf')},headers=h)
    assert again.status_code==202 and again.json['file']['status']=='DUPLICATE'
    assert Question.query.count()==count
    # Newly registered student can launch it immediately, without an approval action.
    student=app.test_client();sh=login(student)
    for mode in ['practice','exam']:
        start=student.post('/api/attempts',json={'paper_id':pid,'mode':mode,'duration_seconds':60},headers=sh)
        assert start.status_code==201,start.json
        assert len(start.json['palette'])==expected

def test_worker_leaves_paused_catalog_alone(app):
    p=seed()
    from backend.models import IngestionBatch,User
    b=IngestionBatch(user_id=User.query.first().id);db.session.add(b);db.session.flush()
    f=IngestionFile(batch_id=b.id,paper_id=p.id,filename='paused.pdf',status='PAUSED',source_url='https://drive.google.com/file/d/paused/view')
    db.session.add(f);db.session.commit()
    assert work_once() is False
    assert f.status=='PAUSED'
