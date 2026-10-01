"""Store encrypted external OAuth credentials.

Revision ID: f12a6d440003
Revises: e51a9c320002
"""
from alembic import op
import sqlalchemy as sa

revision='f12a6d440003'
down_revision='e51a9c320002'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('external_credential',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('provider',sa.String(length=40),nullable=False,unique=True),
        sa.Column('account_email',sa.String(length=254)),
        sa.Column('refresh_token_enc',sa.Text(),nullable=False),
        sa.Column('scope',sa.Text()),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.Column('updated_at',sa.Float(),nullable=False),
    )

def downgrade():
    op.drop_table('external_credential')
