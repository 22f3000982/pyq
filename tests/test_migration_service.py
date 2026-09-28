import sqlite3
import pytest
from sqlalchemy import create_engine
from backend.models import db
from backend.migration_service import backup_sqlite,digest_file,copy_and_verify,verify_import,redact,safe_error,read_only_check,target_identity


def test_readonly_backup_and_refuse_overwrite(tmp_path):
    original=tmp_path/'original.db';backup=tmp_path/'backup.db'
    with sqlite3.connect(original) as c:c.execute('CREATE TABLE example(id INTEGER PRIMARY KEY,value TEXT)');c.execute("INSERT INTO example VALUES(1,'preserve')")
    before=digest_file(original)
    assert backup_sqlite(original,backup)==before
    assert digest_file(original)==before
    with sqlite3.connect(backup) as c:assert c.execute('SELECT value FROM example').fetchone()[0]=='preserve'
    with pytest.raises(ValueError,match='new file'):backup_sqlite(original,backup)
    with pytest.raises(ValueError,match='new file'):backup_sqlite(original,original)


def test_copy_verifies_all_tables_and_rolls_back_on_duplicate(app,tmp_path):
    # Use actual ORM metadata/fixtures and require every imported field to match.
    target=create_engine('sqlite:///'+str(tmp_path/'destination.db'))
    db.metadata.create_all(target)
    with app.app_context():
        copied=copy_and_verify(db.engine,target)
        assert copied['user']['rows']==1
        assert verify_import(db.engine,target)==copied
        with pytest.raises(Exception):copy_and_verify(db.engine,target)
        assert verify_import(db.engine,target)==copied
    target.dispose()


def test_secrets_redacted_and_target_identity_excludes_password():
    secret='private@secret/123';uri='postgresql+psycopg://postgres:private%40secret%2F123@host/db'
    assert secret not in redact(secret,[secret])
    assert 'private' not in redact(uri,[secret])
    assert 'private' not in safe_error(RuntimeError(uri),[secret])['message']
    assert target_identity('postgresql://u:first@host/db')==target_identity('postgresql://u:second@host/db')
    assert target_identity('postgresql://u:first@host/db')!=target_identity('postgresql://u:first@other/db')


def test_connection_check_refuses_sqlite(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'local.db'))
    with pytest.raises(ValueError,match='PostgreSQL'):read_only_check(engine)


def test_postgres_digest_preserves_timestamp_precision():
    from types import SimpleNamespace
    from sqlalchemy import Table,MetaData,Column,Integer,Float
    from backend.migration_service import table_digest
    table=Table('sample',MetaData(),Column('id',Integer,primary_key=True),Column('created_at',Float))
    class Connection:
        def __init__(self,name):
            self.dialect=SimpleNamespace(name=name);self.lossless=name=='sqlite'
        def execute(self,statement):
            if str(statement)=='SET LOCAL extra_float_digits = 3':
                self.lossless=True;return None
            value=1790322148.4193604 if self.lossless else 1790322148.41936
            return SimpleNamespace(mappings=lambda:[{'id':1,'created_at':value}])
    assert table_digest(Connection('postgresql'),table)==table_digest(Connection('sqlite'),table)
