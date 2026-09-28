import json
from sqlalchemy import create_engine,text
from backend.models import db
from backend.migration_service import verified_resume_snapshot,copy_and_verify,target_identity,verify_import
import pytest

def test_resume_requires_exact_original_target_and_remote_contents(tmp_path):
    folder=tmp_path/'migration-backups'/'checkpoint';folder.mkdir(parents=True)
    source=create_engine('sqlite:///'+str(folder/'working.sqlite3'));target=create_engine('sqlite:///'+str(tmp_path/'destination.db'))
    db.metadata.create_all(source);db.metadata.create_all(target)
    with source.begin() as c:c.execute(text("INSERT INTO course(id,name) VALUES (1,'Test course')"))
    tables=copy_and_verify(source,target);uri='postgresql://example:placeholder@host/postgres'
    (folder/'report.json').write_text(json.dumps({'tables':tables,'original_sha256':'sourcehash','target_identity':target_identity(uri)}))
    assert verified_resume_snapshot(tmp_path,'sourcehash',uri,target)==folder/'working.sqlite3'
    assert verified_resume_snapshot(tmp_path,'changed',uri,target) is None
    with target.begin() as c:c.execute(text("UPDATE course SET name='Changed remote data' WHERE id=1"))
    with pytest.raises(RuntimeError,match='differs'):verified_resume_snapshot(tmp_path,'sourcehash',uri,target)
    with target.connect() as c:assert c.execute(text('SELECT name FROM course')).scalar()=='Changed remote data'


def checkpoint_fixture(tmp_path):
    import shutil
    from backend.migration_service import digest_file
    folder=tmp_path/'migration-backups'/'copied';folder.mkdir(parents=True)
    baseline=folder/'original.sqlite3'
    engine=create_engine('sqlite:///'+str(baseline));db.metadata.create_all(engine)
    with engine.begin() as c:c.execute(text("INSERT INTO course(id,name) VALUES (1,'Unchanged course')"))
    engine.dispose()
    shutil.copy2(baseline,folder/'working.sqlite3');shutil.copy2(baseline,tmp_path/'current.sqlite3')
    source=create_engine('sqlite:///'+str(folder/'working.sqlite3'))
    target=create_engine('sqlite:///'+str(tmp_path/'remote.sqlite3'));db.metadata.create_all(target)
    tables=copy_and_verify(source,target);source.dispose()
    uri='postgresql://example:placeholder@host/postgres'
    (folder/'report.json').write_text(json.dumps({'tables':tables,'original_sha256':digest_file(baseline),'target_identity':target_identity(uri)}))
    return folder,tmp_path/'current.sqlite3',target,uri


def test_resume_after_sqlite_header_changes_without_data_changes(tmp_path):
    import sqlite3
    from backend.migration_service import digest_file
    folder,current,target,uri=checkpoint_fixture(tmp_path)
    before=digest_file(current)
    with sqlite3.connect(current) as c:c.execute('PRAGMA user_version=7')
    assert digest_file(current)!=before
    details={};after=digest_file(current)
    assert verified_resume_snapshot(tmp_path,after,uri,target,original_source=current,diagnostics=details)==folder/'working.sqlite3'
    assert details['candidates'][0]['source_match']=='logical_stable_contents'
    assert digest_file(current)==after


def test_resume_never_discards_changed_local_records(tmp_path):
    import sqlite3
    from backend.migration_service import digest_file
    folder,current,target,uri=checkpoint_fixture(tmp_path)
    with sqlite3.connect(current) as c:c.execute("UPDATE course SET name='New local data' WHERE id=1")
    details={}
    with pytest.raises(RuntimeError,match='Local SQLite records or schema changed'):
        verified_resume_snapshot(tmp_path,digest_file(current),uri,target,original_source=current,diagnostics=details)
    assert details['changed_tables']==['course']
    with target.connect() as c:assert c.execute(text('SELECT name FROM course')).scalar()=='Unchanged course'
    with sqlite3.connect(current) as c:assert c.execute('SELECT name FROM course').fetchone()[0]=='New local data'


def test_resume_rejects_modified_checkpoint_even_if_remote_matches(tmp_path):
    from backend.migration_service import digest_file
    folder,current,target,uri=checkpoint_fixture(tmp_path)
    working=create_engine('sqlite:///'+str(folder/'working.sqlite3'))
    for engine in [working,target]:
        with engine.begin() as c:c.execute(text("UPDATE course SET name='Unexpected edit' WHERE id=1"))
    with pytest.raises(RuntimeError,match='recorded import digests'):
        verified_resume_snapshot(tmp_path,digest_file(current),uri,target,original_source=current)


def test_resume_reports_missing_snapshot_without_overwriting(tmp_path):
    from backend.migration_service import digest_file
    folder,current,target,uri=checkpoint_fixture(tmp_path)
    (folder/'working.sqlite3').unlink()
    with pytest.raises(RuntimeError,match='checkpoint files are missing'):
        verified_resume_snapshot(tmp_path,digest_file(current),uri,target,original_source=current)
