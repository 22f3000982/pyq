"""Bounded repair for the swapped Java/App Dev rows in the supplied diploma workbook.

Source pairs come from Copy of Diploma Level Question Papers__.xlsx (2026-10-03),
May/Sep 2025, rows 12/13. Never overwrite an administrator's unrelated source.
"""
import time
from .models import db,Paper,Course,Term,ExamType,IngestionFile,IngestionBatch
from .catalog import source_token
from .acquisition import event

# term, exam, session, incorrect source ID, correct source ID, filename
JAVA_2025 = [
    ('Sep 2025','Quiz 1','','1I6Dyfua62Gei9SWzhIUgRPrrUJSLPF-K','1wNXCXKeK1y-5cSdhzod3eahs1FLc-w_w','cs2005_2025T3_Q1_AN.pdf'),
    ('Sep 2025','Quiz 2','','1EbFytHi2REA7YV_D-IBCvZ0P6wZeSFSl','1uAlBVDg1wRhYgHoChWyIUaUQMuMiS5yU','cs2005_2025T3_Q2_NA.pdf'),
    ('Sep 2025','End Term','AN','1mXXOLvJWeYkXzluNrBn0pkFFfajhOIvT','1TcKuLRT2xl-SI-wxFzltUscuO8_lNmRB','cs2005_2025T3_ET_AN.pdf'),
    ('May 2025','Quiz 1','','12BBjG1-daOhXPfVX6wVchOXyL9soMIQs','1691WYRYCYLc9heZ5iXGKbByvsdqcRRal','cs2005_2025T2_Q1_AN.pdf'),
    ('May 2025','Quiz 2','','1f2rAmoYkOJmRDfp_bToG_aGgaBx2IXNu','1MB0nDXz1-hOJaEtse1v6z0iBwSbyRjNf','cs2005_2025T2_Q2_AN.pdf'),
    ('May 2025','End Term','FN','1ySBpySHA6mSAEI9-BF7BzsJFHQ-fW-ks','1EWysEPyVaTWJBcMeOFi2QfetO1cdz7J7','cs2005_2025T2_ET_FN.pdf'),
    ('May 2025','End Term','AN','14quiXioIyYnmvknR1nPH5zNovtsfZE-9','1tyAZehm2hxI6ZoN8tRjRxTw3QmQN7v7o','cs2005_2025T2_ET_AN.pdf'),
]

def repair_java_2025(user_id,apply=False):
    query=Paper.query.join(Course).join(Term).join(ExamType).filter(Course.code.in_(['CS2003','CS2005']),Term.year==2025,Term.month.in_([5,9]),Paper.status!='ARCHIVED')
    papers=query.with_for_update().all() if apply else query.all()
    changes=[]
    for term,exam,session,wrong,right,name in JAVA_2025:
        matches=[p for p in papers if p.course.code=='CS2005' and p.term.name==term and p.exam_type.name==exam and (p.session or '')==session and source_token(p.source_url)=='drive:'+wrong]
        if len(matches)>1:raise ValueError('Ambiguous Java catalog entries; repair stopped without changes.')
        if matches:changes.append((matches[0],right,name,True))
        # Correct App Dev metadata for subsequent batches, but do not reprocess
        # its bank: the administrator has already replaced the available PDFs.
        app_matches=[p for p in papers if p.course.code=='CS2003' and p.term.name==term and p.exam_type.name==exam and (p.session or '')==session and source_token(p.source_url)=='drive:'+right]
        if len(app_matches)>1:raise ValueError('Ambiguous App Dev catalog entries; repair stopped without changes.')
        if app_matches:changes.append((app_matches[0],wrong,name.replace('cs2005_','cs2003_'),False))
    ids=[p.id for p,_,_,_ in changes]
    active=IngestionFile.query.filter(IngestionFile.paper_id.in_(ids),IngestionFile.status.in_(['QUEUED','FETCH_QUEUED','FETCHING','PROCESSING'])).count() if ids else 0
    items=[{'paper_id':p.id,'term':p.term.name,'exam':p.exam_type.name,'session':p.session,'name':name,'course':p.course.name,'queue':queue} for p,_,name,queue in changes]
    if not apply:return {'items':items,'count':len(items),'active_jobs':active,'applied':False}
    if active:raise ValueError('An affected Java paper is processing. Finish or recover that job before repairing.')
    if not changes:return {'items':[],'count':0,'queued':0,'applied':True,'batch_id':None}
    batch=IngestionBatch(user_id=user_id) if any(queue for _,_,_,queue in changes) else None
    if batch is not None:db.session.add(batch);db.session.flush()
    for p,right,name,queue in changes:
        url='https://drive.google.com/file/d/'+right+'/view?usp=drivesdk'
        p.source_metadata={**(p.source_metadata or {}),'_java_2025_repair':{'old_source':p.source_url,'new_source':url,'at':time.time()}}
        p.source_url=url;p.name=name
        # Existing questions and attempt snapshots stay intact until extraction succeeds.
        if not queue:continue
        f=IngestionFile(batch_id=batch.id,paper_id=p.id,filename=name,source_url=url,status='FETCH_QUEUED')
        db.session.add(f);db.session.flush();event(f,'CATALOG_SOURCE_REPAIR','Confirmed Java row-code/filename repair from the supplied diploma workbook')
    db.session.commit()
    return {'items':items,'count':len(items),'queued':sum(queue for _,_,_,queue in changes),'applied':True,'batch_id':batch.id if batch is not None else None}
