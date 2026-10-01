"""Store anonymous formatting reports for admin review."""
from alembic import op
import sqlalchemy as sa
revision='b24c8f660005'
down_revision='a13b7e550004'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('content_report',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('question_id',sa.Integer(),sa.ForeignKey('question.id'),nullable=False),
        sa.Column('guest_hash',sa.String(64),nullable=False),
        sa.Column('issue',sa.String(20),nullable=False),
        sa.Column('description',sa.String(1000),nullable=False),
        sa.Column('status',sa.String(12),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.Column('resolved_at',sa.Float()),
        sa.UniqueConstraint('question_id','guest_hash',name='uq_content_report_question_guest'))
    op.create_index('ix_content_report_question_id','content_report',['question_id'])
    op.create_index('ix_content_report_status','content_report',['status'])

def downgrade():
    op.drop_table('content_report')
