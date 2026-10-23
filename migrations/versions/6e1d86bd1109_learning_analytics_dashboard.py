"""learning analytics dashboard

Revision ID: 6e1d86bd1109
Revises: d10a00ee0013
Create Date: 2026-10-22 22:49:41.636865

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6e1d86bd1109'
down_revision = 'd10a00ee0013'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('analytics_event',sa.Column('score_percent',sa.Float(),nullable=True))
    op.add_column('analytics_event',sa.Column('exam_name',sa.String(80),nullable=True))
    op.create_table('analytics_question_day',
        sa.Column('day',sa.String(10),primary_key=True),sa.Column('paper_key',sa.String(64),primary_key=True),
        sa.Column('question_id',sa.Integer(),primary_key=True),sa.Column('version',sa.String(64),primary_key=True),
        sa.Column('mode',sa.String(20),primary_key=True),sa.Column('number',sa.String(40),nullable=False),
        *[sa.Column(k,sa.Integer(),nullable=False) for k in ('correct','partial','incorrect','skipped','ungraded')])
    op.create_index('ix_analytics_question_day_question','analytics_question_day',['question_id','day'])
    if op.get_bind().dialect.name=='postgresql':
        # Flask uses the privileged server connection. No browser Data API access.
        for table in ('analytics_event','analytics_question_day'):
            op.execute(sa.text('ALTER TABLE '+table+' ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text('REVOKE ALL ON TABLE '+table+' FROM PUBLIC'))
            for role in ('anon','authenticated'):
                op.execute(sa.text("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"+role+"') THEN REVOKE ALL ON TABLE "+table+" FROM "+role+"; END IF; END $$;"))


def downgrade():
    op.drop_table('analytics_question_day')
    with op.batch_alter_table('analytics_event') as batch:
        batch.drop_column('score_percent');batch.drop_column('exam_name')
