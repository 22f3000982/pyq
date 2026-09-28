"""Latest paper progress and bounded temporary sessions.

Prepared migration only: never applied automatically at startup or by check-db.
Existing question responses are not deleted here. The session worker later
removes expired records. Back up and explicitly authorize activation first.
"""
import time
from alembic import op
import sqlalchemy as sa
revision='d41e7c120001'
down_revision='b323d1f6274d'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('paper_progress',
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('user.id'),primary_key=True),
        sa.Column('paper_id',sa.Integer(),sa.ForeignKey('paper.id'),primary_key=True),
        sa.Column('attempted',sa.Boolean(),nullable=False),
        sa.Column('last_score',sa.Float(),nullable=True),
        sa.Column('last_attempted_at',sa.Float(),nullable=False))
    op.add_column('attempt',sa.Column('expires_at',sa.Float(),nullable=False,server_default='0'))
    op.add_column('attempt',sa.Column('records_progress',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.create_index('ix_attempt_expires_at','attempt',['expires_at'])
    if op.get_bind().dialect.name=='sqlite':
        with op.batch_alter_table('attempt',recreate='always',table_kwargs={'sqlite_autoincrement':True}):
            pass
    bind=op.get_bind();meta=sa.MetaData()
    attempts=sa.Table('attempt',meta,autoload_with=bind)
    progress=sa.Table('paper_progress',meta,autoload_with=bind)
    latest={};now=time.time()
    for a in bind.execute(sa.select(attempts).order_by(attempts.c.submitted_at,attempts.c.id)).mappings():
        eligible=bool(a['paper_id']) and not a['title'].startswith('Wrong-answer practice')
        expiry=((a['submitted_at'] or now)+3600) if a['status']!='ACTIVE' else ((a['deadline']+3600) if a['deadline'] else now+7*86400)
        bind.execute(attempts.update().where(attempts.c.id==a['id']).values(expires_at=expiry,records_progress=eligible))
        if eligible and a['status']=='SUBMITTED' and a['result'] is not None:
            latest[(a['user_id'],a['paper_id'])]={'user_id':a['user_id'],'paper_id':a['paper_id'],'attempted':True,'last_score':a['result'].get('percentage'),'last_attempted_at':a['submitted_at'] or a['started_at']}
    if latest:bind.execute(progress.insert(),list(latest.values()))

def downgrade():
    # Purged session details cannot be reconstructed by a schema downgrade.
    op.drop_index('ix_attempt_expires_at','attempt')
    with op.batch_alter_table('attempt') as batch:
        batch.drop_column('records_progress');batch.drop_column('expires_at')
    op.drop_table('paper_progress')
