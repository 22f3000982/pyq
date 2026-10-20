"""Seed the owner's source questions as private, unvalidated drafts.
No existing question is overwritten; source IDs are stable import identities.
"""
import json,time
from pathlib import Path
from alembic import op
import sqlalchemy as sa
revision='d10a00ee0013'
down_revision='c91a00ee0012'
branch_labels=None
depends_on=None

def upgrade():
    bundles=json.loads((Path(__file__).resolve().parents[2]/'backend/data/oppe/seed-bundles-20261020.json').read_text())
    conn=op.get_bind()
    courses=sa.table('oppe_course',sa.column('id',sa.Integer),sa.column('slug',sa.String))
    questions=sa.table('oppe_question',sa.column('course_id',sa.Integer),sa.column('external_id',sa.String),sa.column('content',sa.JSON),sa.column('status',sa.String),sa.column('validation_hash',sa.String),sa.column('updated_at',sa.Float))
    for bundle in bundles:
        cid=conn.execute(sa.select(courses.c.id).where(courses.c.slug==bundle['course_slug'])).scalar_one()
        existing=set(conn.execute(sa.select(questions.c.external_id).where(questions.c.course_id==cid)).scalars())
        rows=[dict(course_id=cid,external_id=row['external_id'],content=row['content'],status='DRAFT',validation_hash=None,updated_at=time.time()) for row in bundle['questions'] if row['external_id'] not in existing]
        if rows:op.bulk_insert(questions,rows)

def downgrade():
    # Preserve authored/imported content even when rolling back the seed revision.
    # The schema revision below owns explicit table removal.
    pass
