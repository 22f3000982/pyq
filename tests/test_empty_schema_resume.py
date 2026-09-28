import pytest
from sqlalchemy import create_engine,text
from backend.models import db
from backend.migration_service import assert_empty_target,validate_source


def test_empty_schema_resume_and_no_overwrite(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'target.db'))
    assert assert_empty_target(engine) is False
    db.metadata.create_all(engine)
    with pytest.raises(RuntimeError,match='partial'):assert_empty_target(engine)
    with engine.begin() as c:
        c.execute(text('CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL)'))
        c.execute(text("INSERT INTO alembic_version VALUES ('d41e7c120001')"))
    assert assert_empty_target(engine) is True
    with engine.begin() as c:c.execute(text("INSERT INTO course(id,name) VALUES (1,'Source-preservation test')"))
    with pytest.raises(RuntimeError,match='contains data'):assert_empty_target(engine)
    with engine.connect() as c:assert c.execute(text('SELECT count(*) FROM course')).scalar()==1


def test_reject_empty_source(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'empty.db'));db.metadata.create_all(engine)
    with pytest.raises(RuntimeError,match='no paper/question'):validate_source(tmp_path/'empty.db',tmp_path)


def test_recovery_requires_exact_test_identity_and_password():
    from backend.migration_service import confirmed_fixture_accounts
    from werkzeug.security import generate_password_hash
    admin={'id':1,'email':'admin@example.test','name':'Admin','role':'ADMIN','password_hash':generate_password_hash('test-password-123')}
    student={'id':2,'email':'student@example.test','name':'Student','role':'STUDENT','password_hash':generate_password_hash('test-password-123')}
    assert confirmed_fixture_accounts([admin,student])
    assert not confirmed_fixture_accounts([])
    assert not confirmed_fixture_accounts([dict(admin,email='real@example.com')])
    assert not confirmed_fixture_accounts([dict(admin,password_hash=generate_password_hash('real-secret'))])
    assert not confirmed_fixture_accounts([dict(student,role='ADMIN')])
    assert not confirmed_fixture_accounts([admin,admin])


def test_explicit_schema_translation_keeps_public_users_untouched():
    from sqlalchemy import MetaData,Table,Column,Integer,String,event,select
    from sqlalchemy.pool import StaticPool
    engine=create_engine('sqlite://',poolclass=StaticPool)
    @event.listens_for(engine,'connect')
    def attached(connection,record):connection.execute("ATTACH DATABASE ':memory:' AS pyq_test_guard")
    meta=MetaData();users=Table('user',meta,Column('id',Integer,primary_key=True),Column('name',String))
    meta.create_all(engine)
    with engine.begin() as c:c.execute(users.insert(),{'id':1,'name':'real account'})
    isolated=engine.execution_options(schema_translate_map={None:'pyq_test_guard'})
    meta.create_all(isolated)
    with isolated.begin() as c:c.execute(users.insert(),{'id':1,'name':'test account'})
    meta.drop_all(isolated)
    with engine.connect() as c:assert c.execute(select(users.c.name)).scalar_one()=='real account'
