"""Exercise upgrades of an existing bank and submitted attempt, not just fresh imports."""
import hashlib,json
from pathlib import Path
import fitz
from backend.models import *
from backend.ingestion import process_file
from backend.layout_repair import repair_layouts
from backend.engine import question_snapshot,grade
from test_engine import seed

ROOT=Path(__file__).resolve().parents[1]
def test_repair_preserves_ids_grading_and_results(app):
    p=seed();data=(ROOT/'sample-data/ai.pdf').read_bytes();sha=hashlib.sha256(data).hexdigest()
    path=Path(app.config['UPLOAD_DIR'])/(sha+'.pdf');path.write_bytes(data)
    batch=IngestionBatch(user_id=User.query.first().id);db.session.add(batch);db.session.flush()
    f=IngestionFile(batch_id=batch.id,paper_id=p.id,filename='ai.pdf',path=path.name,file_hash=sha);db.session.add(f);db.session.commit();process_file(f.id)
    qs=Question.query.filter_by(paper_id=p.id,status='AVAILABLE').all()
    q=next(q for q in qs if q.images and q.options)
    q.text='Old flattened presentation'
    a=Attempt(user_id=User.query.first().id,paper_id=p.id,mode='practice',title='Saved attempt',status='SUBMITTED',result={'score':q.marks})
    db.session.add(a);db.session.flush()
    item=AttemptAnswer(attempt_id=a.id,question_id=q.id,position=0,snapshot=question_snapshot(q),answer=q.answers,outcome='CORRECT',awarded=q.marks);db.session.add(item)
    db.session.add(Bookmark(user_id=a.user_id,question_id=q.id));db.session.commit()
    before={q.id:(q.answers,q.marks,q.negative_marks) for q in qs};saved=(item.answer,item.awarded,a.result)
    report=repair_layouts();assert report[0]['status']=='COMPLETED',report
    assert report[0]['updated']==26
    assert q.text!='Old flattened presentation' and '[[IMAGE:' in q.text
    assert item.snapshot['text']==q.text
    assert (item.answer,item.awarded,a.result)==saved
    assert {q.id:(q.answers,q.marks,q.negative_marks) for q in qs}==before
    assert db.session.get(Bookmark,(a.user_id,q.id))
    count=Question.query.count();image_count=QuestionImage.query.count()
    report=repair_layouts();assert report[0]['status']=='COMPLETED'
    assert Question.query.count()==count and QuestionImage.query.count()==image_count
