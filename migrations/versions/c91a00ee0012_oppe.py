"""Isolated admin-only OPPE authoring. No changes to PYQ content."""
from alembic import op
import sqlalchemy as sa
revision='c91a00ee0012'
down_revision='b81deeed0011'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('oppe_course',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('slug',sa.String(60),unique=True,nullable=False),sa.Column('name',sa.String(100),nullable=False),sa.Column('language',sa.String(20),nullable=False),sa.Column('categories',sa.JSON(),nullable=False))
    op.create_table('oppe_question',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('course_id',sa.Integer(),sa.ForeignKey('oppe_course.id'),nullable=False),sa.Column('external_id',sa.String(100),nullable=False),sa.Column('content',sa.JSON(),nullable=False),sa.Column('status',sa.String(12),nullable=False),sa.Column('validation_hash',sa.String(64)),sa.Column('updated_at',sa.Float(),nullable=False),sa.UniqueConstraint('course_id','external_id',name='uq_oppe_course_external'))
    op.create_index('ix_oppe_question_course_status','oppe_question',['course_id','status'])
    if op.get_bind().dialect.name=='postgresql':
        # Flask uses its privileged backend connection; no browser Data API access.
        for table in ('oppe_course','oppe_question'):
            op.execute(sa.text('ALTER TABLE '+table+' ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text('REVOKE ALL ON TABLE '+table+' FROM PUBLIC'))
            op.execute(sa.text('REVOKE ALL ON SEQUENCE '+table+'_id_seq FROM PUBLIC'))
            for role in ('anon','authenticated'):
                op.execute(sa.text("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"+role+"') THEN REVOKE ALL ON TABLE "+table+" FROM "+role+"; REVOKE ALL ON SEQUENCE "+table+"_id_seq FROM "+role+"; END IF; END $$;"))
    courses=sa.table('oppe_course',sa.column('slug',sa.String),sa.column('name',sa.String),sa.column('language',sa.String),sa.column('categories',sa.JSON))
    op.bulk_insert(courses,[dict(slug=s,name=n,language=l,categories=['OPPE1','OPPE2']) for s,n,l in [('python','Python','python'),('dbms','DBMS','postgresql'),('pdsa','PDSA','python'),('java','Java','java'),('sc','SC — System Commands','shell')]])

def downgrade():
    op.drop_table('oppe_question');op.drop_table('oppe_course')
