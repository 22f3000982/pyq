"""Anonymous permanent daily analytics and bounded-lifetime deduplication receipts."""
from alembic import op
import sqlalchemy as sa
revision='f68abcaa0009'
down_revision='e57fab990008'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('attempt',sa.Column('analytics_context',sa.JSON(),nullable=True))
    op.create_table('analytics_receipt',sa.Column('key',sa.String(80),primary_key=True),sa.Column('started_at',sa.Float(),nullable=False),sa.Column('completed',sa.Boolean(),nullable=False))
    op.create_index('ix_analytics_receipt_started_at','analytics_receipt',['started_at'])
    op.create_table('analytics_daily',
        sa.Column('day',sa.String(10),primary_key=True),sa.Column('paper_key',sa.String(64),primary_key=True),
        sa.Column('mode',sa.String(20),primary_key=True),sa.Column('device',sa.String(12),primary_key=True),
        sa.Column('paper_name',sa.String(300),nullable=False),sa.Column('course_key',sa.String(64),nullable=False),
        sa.Column('course_name',sa.String(200),nullable=False),sa.Column('starts',sa.Integer(),nullable=False),
        sa.Column('completions',sa.Integer(),nullable=False),sa.Column('automatic',sa.Integer(),nullable=False),
        sa.Column('elapsed_seconds',sa.Float(),nullable=False))
    op.create_index('ix_analytics_daily_course_day','analytics_daily',['course_key','day'])

def downgrade():
    op.drop_table('analytics_daily')
    op.drop_table('analytics_receipt')
    with op.batch_alter_table('attempt') as batch:
        batch.drop_column('analytics_context')
