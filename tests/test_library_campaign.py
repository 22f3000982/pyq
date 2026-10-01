import io
import openpyxl
from backend.models import db,User,Course,Term,ExamType,Paper,Question,QuestionOption,QuestionImage,PaperProgress,Attempt,AttemptAnswer,Bookmark,IngestionBatch,IngestionFile,SourceEntry
from conftest import login


def workbook():
    wb=openpyxl.Workbook()
    master=wb.active;master.title='Courses'
    master.append(['Course Name','Course Code','Course Level','Course Type'])
    master.append(['Deep Learning','DL','Diploma','Theory'])
    q1=wb.create_sheet('May 2026');q1.append(['Course Name','Quiz 1','Quiz 2','FN End Term','AN End Term'])
    for row,name in enumerate(['Deep Learning'],2):
        q1.cell(row,1,name)
        for col,(label,key) in enumerate([('Q1','q1'),('Q2','q2'),('FN','fn'),('AN','an')],2):
            q1.cell(row,col,label);q1.cell(row,col).hyperlink=f'https://drive.google.com/file/d/{key}/view'
    jan=wb.create_sheet('Jan 2026');jan.append(['Course Name','Quiz 1'])
    jan.append(['Deep Learning','Old Q1']);jan['B2'].hyperlink='https://drive.google.com/file/d/q1-old/view'
    out=io.BytesIO();wb.save(out);wb.close();return out.getvalue()


def post_xlsx(client,url,h,data):
    return client.post(url,headers=h,data={'file':(io.BytesIO(data),'catalog.xlsx')},content_type='multipart/form-data')


def test_fresh_catalog_refresh_and_campaign_order(app,client):
    h=login(client,True)
    r=post_xlsx(client,'/api/admin/catalog/refresh',h,workbook())
    assert r.status_code==201
    assert r.json['queued']==0
    campaign=client.get('/api/admin/catalog/campaign',headers=h).json
    assert campaign['total']==5
    assert campaign['current']['label']=='Quiz 1'
    assert campaign['current']['term']=='May 2026'
    labels=[(g['label'],g['term']) for g in campaign['groups']]
    assert labels[:2]==[('Quiz 1','May 2026'),('Quiz 1','Jan 2026')]
    assert ('Quiz 2','May 2026') in labels
    assert ('End Term · FN','May 2026') in labels
    assert ('End Term · AN','May 2026') in labels


def test_campaign_processes_only_current_group(app,client):
    h=login(client,True);post_xlsx(client,'/api/admin/catalog/refresh',h,workbook())
    campaign=client.get('/api/admin/catalog/campaign',headers=h).json
    current=campaign['current']
    r=client.post('/api/admin/catalog/campaign/process',headers=h,json={'stage':current['stage'],'term_id':current['term_id'],'limit':20})
    assert r.status_code==202 and r.json['queued']==1
    queued=IngestionFile.query.all()
    assert len(queued)==1
    p=db.session.get(Paper,queued[0].paper_id)
    assert p.exam_type.name=='Quiz 1' and p.term.name=='May 2026'


def test_controlled_reset_keeps_users_and_clears_library(app,client):
    h=login(client,True);post_xlsx(client,'/api/admin/catalog/refresh',h,workbook())
    p=Paper.query.first();q=Question(paper_id=p.id,number='1',kind='MCQ',text='Q',answers=['A'],answer_status='ANSWER_AVAILABLE',status='AVAILABLE')
    db.session.add(q);db.session.flush()
    db.session.add(QuestionOption(question_id=q.id,key='A',text='A',position=0))
    db.session.add(QuestionImage(question_id=q.id,path='asset.png'))
    student=User(email='s@example.test',name='S',password_hash='x');db.session.add(student);db.session.flush()
    db.session.add(PaperProgress(user_id=student.id,paper_id=p.id,attempted=True,last_score=50,last_attempted_at=1))
    a=Attempt(user_id=student.id,paper_id=p.id,mode='exam',title='x',expires_at=9999999999);db.session.add(a);db.session.flush()
    db.session.add(AttemptAnswer(attempt_id=a.id,question_id=q.id,position=1,snapshot={'id':q.id}))
    db.session.add(Bookmark(user_id=student.id,question_id=q.id));db.session.commit()
    preview=client.get('/api/admin/library-reset/preview',headers=h)
    assert preview.status_code==200 and preview.json['counts']['papers']==5
    bad=client.post('/api/admin/library-reset',headers=h,json={'confirmation':'wrong','cleanup_storage':False})
    assert bad.status_code==400
    done=client.post('/api/admin/library-reset',headers=h,json={'confirmation':'RESET PYQ LIBRARY','cleanup_storage':False})
    assert done.status_code==200
    assert User.query.count()==2
    assert Paper.query.count()==Question.query.count()==Course.query.count()==0
    assert Attempt.query.count()==PaperProgress.query.count()==Bookmark.query.count()==0
