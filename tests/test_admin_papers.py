from backend.models import db,Course,Term,ExamType,Paper,Question
from conftest import login


def seed_papers():
    c=Course(name='Deep Learning',code='DL')
    t=Term(name='May 2026',year=2026,month=5)
    q1=ExamType(name='Quiz 1');q2=ExamType(name='Quiz 2');et=ExamType(name='End Term')
    db.session.add_all([c,t,q1,q2,et]);db.session.flush()
    papers=[]
    for n,e in enumerate((q1,q2,et),1):
        p=Paper(identity=f'admin-paper-{n}',course_id=c.id,term_id=t.id,exam_type_id=e.id,name=f'Paper {n}',status='AVAILABLE')
        db.session.add(p);db.session.flush()
        db.session.add(Question(paper_id=p.id,number='1',kind='NAT',text='Value?',status='AVAILABLE',answers=1,answer_status='ANSWER_AVAILABLE',marks=1))
        papers.append(p)
    empty=Paper(identity='admin-empty',course_id=c.id,term_id=t.id,exam_type_id=q1.id,name='Unwanted empty paper',status='CATALOG_ONLY')
    db.session.add(empty);db.session.commit()
    return c,papers,empty


def test_admin_paper_crud_archive_restore_and_safe_delete(app,client):
    c,papers,empty=seed_papers();h=login(client,True)
    listing=client.get('/api/admin/papers?limit=100')
    assert listing.status_code==200 and listing.json['total']==4

    target=papers[0]
    edited=client.patch(f'/api/admin/papers/{target.id}',headers=h,json={'name':'Quiz 1 revised','session':'FN'})
    assert edited.status_code==200 and edited.json['name']=='Quiz 1 revised' and edited.json['session']=='FN'

    archived=client.post(f'/api/admin/papers/{target.id}/archive',headers=h,json={})
    assert archived.status_code==200 and archived.json['archived'] is True
    assert client.get(f'/api/papers/{target.id}').status_code==404
    public=client.get('/api/papers?limit=100').json
    assert target.id not in [p['id'] for p in public['items']]

    stats=client.get('/api/stats').json
    assert stats['exam_papers']['Quiz 1']==0
    assert stats['exam_papers']['Quiz 2']==1 and stats['exam_papers']['End Term']==1

    restored=client.post(f'/api/admin/papers/{target.id}/restore',headers=h,json={})
    assert restored.status_code==200 and restored.json['archived'] is False
    assert client.get(f'/api/papers/{target.id}').status_code==200
    assert client.get('/api/stats').json['exam_papers']['Quiz 1']==1

    blocked=client.delete(f'/api/admin/papers/{target.id}',headers=h)
    assert blocked.status_code==409 and 'Archive it instead' in blocked.json['message']

    deleted=client.delete(f'/api/admin/papers/{empty.id}',headers=h)
    assert deleted.status_code==200 and deleted.json['deleted'] is True
    assert db.session.get(Paper,empty.id) is None


def test_non_admin_cannot_manage_papers(app,client):
    _,papers,_=seed_papers();h=login(client)
    assert client.get('/api/admin/papers').status_code==403
    assert client.post(f'/api/admin/papers/{papers[0].id}/archive',headers=h,json={}).status_code==403
