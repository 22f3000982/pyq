"""Local-worker solution queue and published text."""
from alembic import op
import sqlalchemy as sa
revision='e57fab990008'
down_revision='d46eab880007'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('ai_solution',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('question_id',sa.Integer(),sa.ForeignKey('question.id',ondelete='CASCADE'),nullable=False,unique=True),sa.Column('version',sa.String(64),nullable=False),sa.Column('text',sa.Text(),nullable=False),sa.Column('final_answer',sa.JSON()),sa.Column('status',sa.String(24),nullable=False),sa.Column('provider',sa.String(30)),sa.Column('model',sa.String(100)),sa.Column('prompt_version',sa.String(30)),sa.Column('checks',sa.JSON()),sa.Column('updated_at',sa.Float()))
    op.create_index('ix_ai_solution_status','ai_solution',['status'])
    op.create_table('solution_batch',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('status',sa.String(24),nullable=False),sa.Column('created_at',sa.Float()),sa.Column('worker_seen',sa.Float()))
    op.create_table('solution_job',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('batch_id',sa.Integer(),sa.ForeignKey('solution_batch.id',ondelete='CASCADE'),nullable=False),sa.Column('question_id',sa.Integer(),sa.ForeignKey('question.id',ondelete='CASCADE'),nullable=False,unique=True),sa.Column('version',sa.String(64),nullable=False),sa.Column('status',sa.String(24),nullable=False),sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('lease_token',sa.String(64)),sa.Column('lease_until',sa.Float()),sa.Column('retry_at',sa.Float(),nullable=False),sa.Column('error',sa.String(240)))
    op.create_index('ix_solution_job_batch_id','solution_job',['batch_id'])
    op.create_index('ix_solution_job_status','solution_job',['status'])

def downgrade():
    op.drop_table('solution_job')
    op.drop_table('solution_batch')
    op.drop_table('ai_solution')
