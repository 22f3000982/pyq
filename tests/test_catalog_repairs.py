from backend.models import db,Course,Term,ExamType,Paper,Question,IngestionFile,IngestionBatch
from backend.catalog_repairs import JAVA_2025
from backend.catalog import source_token
from conftest import login


def seed_repair():
    java=Course(name='Programming Concepts using Java',code='CS2005')
    appdev=Course(name='Application Development - 1',code='CS2003')
    term=Term(name='Sep 2025',year=2025,month=9);exam=ExamType(name='Quiz 1')
    db.session.add_all([java,appdev,term,exam]);db.session.flush()
    wrong,right=JAVA_2025[0][3:5]
    p=Paper(identity='java',course_id=java.id,term_id=term.id,exam_type_id=exam.id,name='cs2003_2025T3_Q1_AN.pdf',source_url='https://drive.google.com/file/d/'+wrong+'/view',status='AVAILABLE')
    corrected=Paper(identity='appdev',course_id=appdev.id,term_id=term.id,exam_type_id=exam.id,name='cs2005_2025T3_Q1_AN.pdf',source_url='https://drive.google.com/file/d/'+right+'/view',status='AVAILABLE')
    db.session.add_all([p,corrected]);db.session.flush()
    for paper in [p,corrected]:db.session.add(Question(paper_id=paper.id,number='1',kind='NAT',text='Retained bank',answers=1,status='AVAILABLE'))
    db.session.commit();return p,corrected


def test_repair_preview_admin_only_apply_idempotent_and_preserves_appdev(app,client):
    p,corrected=seed_repair();old=p.source_url;appurl=corrected.source_url
    h=login(client)
    assert client.post('/api/admin/catalog/repair-java-2025',headers=h,json={}).status_code==401
    h=login(client,True)
    r=client.post('/api/admin/catalog/repair-java-2025',headers=h,json={})
    assert r.status_code==200 and r.json['count']==2 and not r.json['applied']
    assert p.source_url==old and IngestionFile.query.count()==0
    r=client.post('/api/admin/catalog/repair-java-2025',headers=h,json={'apply':True})
    assert r.status_code==200 and r.json['queued']==1
    assert source_token(p.source_url)==source_token(appurl) and source_token(corrected.source_url)==source_token(old)
    assert p.name.startswith('cs2005') and corrected.name.startswith('cs2003') and Question.query.count()==2
    assert IngestionFile.query.one().status=='FETCH_QUEUED'
    again=client.post('/api/admin/catalog/repair-java-2025',headers=h,json={'apply':True})
    assert again.json['queued']==0 and IngestionFile.query.count()==1


def test_repair_does_not_overwrite_manual_source_and_blocks_active_jobs(app,client):
    p,corrected=seed_repair();h=login(client,True)
    batch=IngestionBatch(user_id=1);db.session.add(batch);db.session.flush()
    f=IngestionFile(batch_id=batch.id,paper_id=p.id,filename='java.pdf',status='QUEUED');db.session.add(f);db.session.commit()
    old=p.source_url
    r=client.post('/api/admin/catalog/repair-java-2025',headers=h,json={'apply':True})
    assert r.status_code==409
    db.session.refresh(p);assert p.source_url==old
    p.source_url='https://example.com/admin-corrected.pdf';db.session.commit()
    r=client.post('/api/admin/catalog/repair-java-2025',headers=h,json={'apply':True})
    assert r.status_code==200 and r.json['queued']==0
    assert p.source_url=='https://example.com/admin-corrected.pdf'
