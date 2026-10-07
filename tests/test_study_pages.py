from backend.models import db,Course,Term,ExamType,Paper,Question,AISolution,Attempt
from backend.ai_solutions import snapshot,version
from conftest import login

def seed():
    c=Course(name='Test maths',code='MA1');t=Term(name='May 2026',year=2026,month=5);e=ExamType(name='Quiz 1')
    db.session.add_all([c,t,e]);db.session.flush()
    p=Paper(identity='study-test',name='Maths Quiz 1',course_id=c.id,term_id=t.id,exam_type_id=e.id,status='AVAILABLE')
    db.session.add(p);db.session.flush()
    q=Question(paper_id=p.id,number='1',kind='NAT',text='Compute \\(2+2\\) <script>bad</script>',status='AVAILABLE')
    hidden=Question(paper_id=p.id,number='2',kind='NAT',text='HIDDEN SECRET',status='HIDDEN')
    db.session.add_all([q,hidden]);db.session.flush()
    s=AISolution(question_id=q.id,version=version(snapshot(q)),text='PUBLISHED EXPLANATION',status='PUBLISHED');db.session.add(s);db.session.commit()
    return c,p,q,s

def test_public_reading_without_session_and_solution_guards(app,client):
    c,p,q,s=seed()
    assert 'Test maths' in client.get('/study').text
    assert 'Maths Quiz 1' in client.get(f'/study/courses/{c.id}').text
    response=client.get(f'/study/papers/{p.id}')
    assert response.status_code==200
    assert 'PUBLISHED EXPLANATION' in response.text and 'HIDDEN SECRET' not in response.text
    assert '<script>bad</script>' not in response.text
    assert Attempt.query.count()==0
    assert 'Set-Cookie' not in response.headers
    s.status='DRAFT';db.session.commit()
    assert 'PUBLISHED EXPLANATION' not in client.get(f'/study/papers/{p.id}').text
    s.status='PUBLISHED';s.version='outdated';db.session.commit()
    assert 'PUBLISHED EXPLANATION' not in client.get(f'/study/papers/{p.id}').text
    p.status='ARCHIVED';db.session.commit()
    assert client.get(f'/study/papers/{p.id}').status_code==404
    assert client.get('/study/papers/99999').status_code==404

def test_contact_admin_email_is_validated_and_public(client):
    assert client.get('/contact').status_code==200
    headers=login(client,admin=True)
    assert client.put('/api/admin/about',json={'contact_email':'x\nInjected'},headers=headers).status_code==400
    assert client.put('/api/admin/about',json={'contact_email':'support@example.test'},headers=headers).status_code==200
    assert 'mailto:support@example.test' in client.get('/contact').text
    assert 'content removal' in client.get('/contact').text.lower()

def test_study_search_and_theme(app,client):
    c,p,q,s=seed()
    assert 'Test maths' in client.get('/study?q=MA1').text
    assert 'Test maths' not in client.get('/study?q=unmatched').text
    assert 'Maths Quiz 1' in client.get(f'/study/courses/{c.id}?q=May').text
    assert 'No papers match' in client.get(f'/study/courses/{c.id}?q=unmatched').text
    assert 'study-theme-toggle' in client.get('/contact').text
    assert 'study-theme.js' in client.get('/study').text
