"""Automatic extraction evidence and acquisition; additive, data-preserving."""
from alembic import op
import sqlalchemy as sa
revision='b323d1f6274d'
down_revision='c60248414d44'
branch_labels=None
depends_on=None

def upgrade():
    fields={'ingestion_file':[('source_url',sa.Text()),('events',sa.JSON())], 'paper':[('source_metadata',sa.JSON())], 'question':[('source_pages',sa.JSON()),('evidence',sa.JSON()),('fingerprint',sa.String(64))], 'question_image':[('option_key',sa.String(20)),('source_page',sa.Integer())]}
    for table,columns in fields.items():
        for name,type_ in columns:op.add_column(table,sa.Column(name,type_,nullable=True))
    for table,column in [('ingestion_file','duplicate_of_id'),('paper','canonical_paper_id')]:
        if op.get_bind().dialect.name=='sqlite':op.execute(f'ALTER TABLE {table} ADD COLUMN {column} INTEGER REFERENCES {table}(id)')
        else:op.add_column(table,sa.Column(column,sa.Integer(),sa.ForeignKey(table+'.id',name=f'fk_{table}_{column}')))
    op.create_index('ix_question_fingerprint','question',['fingerprint'])

def downgrade():
    op.drop_index('ix_question_fingerprint','question')
    for table,columns in {'question_image':['option_key','source_page'],'question':['source_pages','evidence','fingerprint'],'paper':['canonical_paper_id','source_metadata'],'ingestion_file':['duplicate_of_id','events','source_url']}.items():
        for column in columns:op.drop_column(table,column)
