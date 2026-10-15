"""Private contact inbox and public editorial tools; preserve all existing content."""
from alembic import op
import sqlalchemy as sa
revision='b81deeed0011'
down_revision='a79bcdaa0010'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('contact_message',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('name',sa.String(100),nullable=False),sa.Column('email',sa.String(254),nullable=False),sa.Column('topic',sa.String(40),nullable=False),sa.Column('message',sa.Text(),nullable=False),sa.Column('status',sa.String(12),nullable=False),sa.Column('created_at',sa.Float(),nullable=False))
    op.create_index('ix_contact_message_status_id','contact_message',['status','id'])
    op.create_table('course_guide',sa.Column('course_id',sa.Integer(),sa.ForeignKey('course.id',ondelete='CASCADE'),primary_key=True),*[sa.Column(k,sa.Text(),nullable=False) for k in ('introduction','topics','prerequisites','mistakes','practice')],sa.Column('published',sa.Boolean(),nullable=False))
    op.create_table('content_quality_review',sa.Column('question_id',sa.Integer(),sa.ForeignKey('question.id',ondelete='CASCADE'),primary_key=True),sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('checks',sa.JSON(),nullable=False),sa.Column('reviewed_at',sa.Float(),nullable=False))
    op.create_table('study_paper_settings',sa.Column('paper_id',sa.Integer(),sa.ForeignKey('paper.id',ondelete='CASCADE'),primary_key=True),sa.Column('featured',sa.Boolean(),nullable=False),sa.Column('allow_ads',sa.Boolean(),nullable=False))

def downgrade():
    for table in ('study_paper_settings','content_quality_review','course_guide','contact_message'):op.drop_table(table)
