"""Allow browser-owned temporary sessions without creating student accounts."""
from alembic import op
import sqlalchemy as sa
revision='a13b7e550004'
down_revision='f12a6d440003'
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    sequence=bind.execute(sa.text("SELECT seq FROM sqlite_sequence WHERE name='attempt'")).scalar() if bind.dialect.name=='sqlite' else None
    with op.batch_alter_table('attempt',table_kwargs={'sqlite_autoincrement':True}) as batch:
        batch.alter_column('user_id',existing_type=sa.Integer(),nullable=True)
        batch.add_column(sa.Column('guest_hash',sa.String(64),nullable=True))
        batch.create_index('ix_attempt_guest_hash',['guest_hash'])
    if sequence is not None:
        bind.execute(sa.text("UPDATE sqlite_sequence SET seq=MAX(seq,:sequence) WHERE name='attempt'"),{'sequence':sequence})

def downgrade():
    # Guest sessions are temporary; remove them before restoring the user FK requirement.
    op.execute('DELETE FROM attempt_answer WHERE attempt_id IN (SELECT id FROM attempt WHERE user_id IS NULL)')
    op.execute('DELETE FROM attempt WHERE user_id IS NULL')
    with op.batch_alter_table('attempt',table_kwargs={'sqlite_autoincrement':True}) as batch:
        batch.drop_index('ix_attempt_guest_hash')
        batch.drop_column('guest_hash')
        batch.alter_column('user_id',existing_type=sa.Integer(),nullable=False)
