"""Composite indexes for actual paper/session/ingestion filters.

Revision ID: e51a9c320002
Revises: d41e7c120001
"""
from alembic import op
revision='e51a9c320002'
down_revision='d41e7c120001'
branch_labels=None
depends_on=None

INDEXES=[('ix_question_paper_status_id','question',['paper_id','status','id']),
         ('ix_attempt_user_status','attempt',['user_id','status']),
         ('ix_ingestion_file_status_id','ingestion_file',['status','id'])]

def upgrade():
    if op.get_bind().dialect.name=='postgresql':
        with op.get_context().autocommit_block():
            for name,table,columns in INDEXES:
                op.create_index(name,table,columns,postgresql_concurrently=True,if_not_exists=True)
    else:
        for name,table,columns in INDEXES:op.create_index(name,table,columns)

def downgrade():
    for name,table,_ in reversed(INDEXES):op.drop_index(name,table_name=table)
