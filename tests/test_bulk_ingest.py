from backend.models import Course,Term,ExamType,Paper,IngestionBatch,IngestionFile,User,db
from bulk_ingest import candidates

def paper(identity,name):
    c=Course(name='Bulk '+identity,code='BULK-'+identity)
    t=Term(name='Bulk '+identity,year=2030,month=1)
    e=ExamType(name='Bulk '+identity)
    db.session.add_all([c,t,e]);db.session.flush()
    p=Paper(identity=identity,course_id=c.id,term_id=t.id,exam_type_id=e.id,name=name,source_url='https://example.test/'+identity+'.pdf',status='CATALOG_ONLY')
    db.session.add(p);db.session.flush();return p

def test_bulk_candidates_are_bounded_and_retry_only_failed(app):
    with app.app_context():
        p1=paper('bulk-one','One');p2=paper('bulk-two','Two');p3=paper('bulk-three','Three');p4=paper('bulk-four','Four')
        u=User.query.first();batch=IngestionBatch(user_id=u.id);db.session.add(batch);db.session.flush()
        db.session.add_all([
            IngestionFile(batch_id=batch.id,paper_id=p2.id,filename='two.pdf',status='AVAILABLE'),
            IngestionFile(batch_id=batch.id,paper_id=p3.id,filename='three.pdf',status='PROCESSING_FAILED'),
            IngestionFile(batch_id=batch.id,paper_id=p4.id,filename='four.pdf',status='PAUSED'),
        ]);db.session.commit()
        assert candidates(20,False)==[p1.id]
        assert candidates(20,True)==[p1.id,p3.id]
        db.session.remove()
