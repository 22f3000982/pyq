from conftest import login
from test_engine import seed
from backend.models import db,Course,Term,ExamType,Paper,Question

def test_solution_summary_combines_scope_filters_and_statistics(client):
    base=seed();base.course.level='degree';db.session.commit()
    c=Course(name='Foundation Python',level='foundation');t=Term(name='May 2025',year=2025,month=5);et=ExamType(name='End Term')
    db.session.add_all([c,t,et]);db.session.flush()
    for i,(year,month,session) in enumerate([(2025,5,'FN'),(2025,5,'AN'),(2026,5,'FN'),(2025,9,'FN')]):
        term=t
        if (year,month)!=(2025,5):
            term=Term(name=f'Term {month} {year}',year=year,month=month);db.session.add(term);db.session.flush()
        p=Paper(identity='scope-'+str(i),name='Paper '+str(i),course_id=c.id,term_id=term.id,exam_type_id=et.id,session=session,status='AVAILABLE')
        db.session.add(p);db.session.flush();db.session.add(Question(paper_id=p.id,number='1',kind='NAT',text='Example',status='AVAILABLE'))
    db.session.commit();login(client,True)
    url='/api/admin/ai-solutions/summary'
    result=client.get(url,query_string=dict(level='foundation',year=2025,month=5,session='AN',course_id=c.id,exam_type_id=et.id))
    assert result.status_code==200
    assert [p['name'] for p in result.json['papers']]==['Paper 1']
    assert result.json['statistics']['papers_total']==1
    assert result.json['statistics']['questions_total']==1
    assert client.get(url,query_string=dict(level='degree')).json['statistics']['papers_total']==1
    assert client.get(url,query_string=dict(level='foundation',year=2024)).json['statistics']['papers_total']==0
    for params in ({'month':13},{'session':'EVENING'},{'level':'invalid'},{'year':'abc'}):assert client.get(url,query_string=params).status_code==400
