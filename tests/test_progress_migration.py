from pathlib import Path
import time
import sqlalchemy as sa
from flask_migrate import upgrade
from backend import create_app
from backend.models import db

MIGRATIONS=str(Path(__file__).resolve().parents[1]/'migrations')

def test_existing_history_backfill_without_touching_active_sessions(tmp_path):
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'migration.db'),'UPLOAD_DIR':str(tmp_path/'uploads'),'RATELIMIT_ENABLED':False})
    with app.app_context():
        upgrade(directory=MIGRATIONS,revision='b323d1f6274d')
        meta=sa.MetaData();meta.reflect(bind=db.engine)
        now=time.time()
        with db.engine.begin() as c:
            c.execute(meta.tables['user'].insert(),{'id':1,'email':'migration@example.test','name':'Migration test','password_hash':'test-only','role':'USER','active':True})
            c.execute(meta.tables['course'].insert(),{'id':1,'name':'Course','code':'C'})
            c.execute(meta.tables['term'].insert(),{'id':1,'name':'May 2026','year':2026,'month':5})
            c.execute(meta.tables['exam_type'].insert(),{'id':1,'name':'Quiz 1'})
            c.execute(meta.tables['paper'].insert(),{'id':1,'identity':'paper','name':'Paper','course_id':1,'term_id':1,'exam_type_id':1})
            for n,score in enumerate((70,90,80),1):
                c.execute(meta.tables['attempt'].insert(),{'id':n,'user_id':1,'paper_id':1,'mode':'exam','title':'Paper','status':'SUBMITTED','started_at':now-200+n,'submitted_at':now-100+n,'result':{'percentage':score},'version':1})
            c.execute(meta.tables['attempt'].insert(),{'id':4,'user_id':1,'paper_id':1,'mode':'exam','title':'Paper','status':'ACTIVE','started_at':now,'deadline':now+5400,'version':1})
            c.execute(meta.tables['question'].insert(),{'id':1,'paper_id':1,'number':'1','kind':'NAT','text':'Fixture','marks':1})
            c.execute(meta.tables['attempt_answer'].insert(),{'id':1,'attempt_id':4,'question_id':1,'position':0,'snapshot':{'number':'1','kind':'NAT'},'answer':'42'})

        upgrade(directory=MIGRATIONS)
        from backend.models import PaperProgress,Attempt
        assert PaperProgress.query.count()==1
        assert PaperProgress.query.one().last_score==80
        active=db.session.get(Attempt,4)
        assert active.status=='ACTIVE' and active.deadline==now+5400
        assert active.expires_at==active.deadline+3600
        assert active.items[0].answer=='42'
        # Migration itself doesn't delete historical records; retention worker does.
        assert Attempt.query.count()==4
        with db.engine.connect() as connection:
            assert 'AUTOINCREMENT' in connection.execute(sa.text("SELECT sql FROM sqlite_master WHERE name='attempt'")).scalar_one()
        from backend.engine import cleanup_sessions
        cleanup_sessions(now+3601)
        assert Attempt.query.count()==1 and PaperProgress.query.one().last_score==80
        assert sa.inspect(db.engine).get_pk_constraint('paper_progress')['constrained_columns']==['user_id','paper_id']
        db.session.remove();db.engine.dispose()
