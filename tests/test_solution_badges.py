from test_engine import seed
from backend.models import db,Question,AISolution
from backend.engine import question_snapshot
from backend.ai_solutions import version
from backend.api import paper_rows

def test_card_counts_only_current_published_visible_solutions(app):
    p=seed()
    qs=Question.query.filter_by(paper_id=p.id).all()
    total=sum(q.status=='AVAILABLE' for q in qs)
    q=qs[0]
    s=AISolution(question_id=q.id,version=version(question_snapshot(q)),text='Reviewed explanation',status='PUBLISHED')
    db.session.add(s);db.session.commit()
    assert paper_rows([p])[0]['solution_coverage']=={'total':total,'published':1}
    s.status='DRAFT';db.session.commit()
    assert paper_rows([p])[0]['solution_coverage']['published']==0
    s.status='PUBLISHED';q.text+=' updated';db.session.commit()
    assert paper_rows([p])[0]['solution_coverage']['published']==0
    s.version=version(question_snapshot(q));q.status='HIDDEN';db.session.commit()
    assert paper_rows([p])[0]['solution_coverage']=={'total':total-1,'published':0}
