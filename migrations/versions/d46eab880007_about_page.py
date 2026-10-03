"""Persistent editable About page."""
from alembic import op
import sqlalchemy as sa
revision = 'd46eab880007'
down_revision = 'c35d9a770006'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('about_page', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('details', sa.JSON(), nullable=False), sa.Column('photo_path', sa.String(255)))

def downgrade():
    op.drop_table('about_page')
