"""Durable usage ledger; preserve previous deployed analytics schema."""
from alembic import op
import sqlalchemy as sa
revision='a79bcdaa0010'
down_revision='f68abcaa0009'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('analytics_event',
        sa.Column('key',sa.String(80),primary_key=True),sa.Column('started_at',sa.Float(),nullable=False),
        sa.Column('start_day',sa.String(10),nullable=False),sa.Column('completed_at',sa.Float()),
        sa.Column('browser_key',sa.String(64),nullable=False),sa.Column('paper_key',sa.String(64),nullable=False),
        sa.Column('paper_name',sa.String(300),nullable=False),sa.Column('course_key',sa.String(64),nullable=False),
        sa.Column('course_name',sa.String(200),nullable=False),sa.Column('initial_mode',sa.String(20),nullable=False),
        sa.Column('completion_mode',sa.String(20)),sa.Column('device',sa.String(12),nullable=False),
        sa.Column('automatic',sa.Boolean(),nullable=False),sa.Column('expires_at',sa.Float(),nullable=False))
    for name in ('started_at','start_day','browser_key'):
        op.create_index('ix_analytics_event_'+name,'analytics_event',[name])
    op.create_index('ix_analytics_event_course_day','analytics_event',['course_key','start_day'])

def downgrade():
    op.drop_table('analytics_event')
