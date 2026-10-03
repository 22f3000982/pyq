"""Mark the existing catalog as Degree; future imports choose their level."""
from alembic import op
import sqlalchemy as sa
revision='c35d9a770006'
down_revision='b24c8f660005'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().execute(sa.text("UPDATE course SET level = 'Degree'"))

def downgrade():
    pass  # Retain accurate content metadata when reverting code.
