import pytest,os,uuid
from sqlalchemy import create_engine,text,inspect
from sqlalchemy.engine import make_url
from backend import create_app
from backend.models import db,User
from werkzeug.security import generate_password_hash

@pytest.fixture(scope='session')
def remote_test_schema():
    remote=os.getenv('PYQ_TEST_DATABASE_URL')
    if not remote:
        yield None
        return
    from backend.database_config import database_url,engine_options
    remote=database_url(remote,'')
    if make_url(remote).get_backend_name()!='postgresql':raise RuntimeError('PYQ_TEST_DATABASE_URL must be PostgreSQL')
    schema='pyq_test_'+uuid.uuid4().hex
    options=engine_options(remote)
    # Qualify every ORM table explicitly. Do NOT depend on pooler search_path.
    options['execution_options']={'schema_translate_map':{None:schema}}
    engine=create_engine(remote,**options)
    try:
        with engine.begin() as conn:conn.execute(text('CREATE SCHEMA "'+schema+'"'))
        db.metadata.create_all(engine)
        if not set(db.metadata.tables).issubset(inspect(engine).get_table_names(schema=schema)):
            raise RuntimeError('Test schema isolation could not be verified')
        yield remote,options,schema,engine
    finally:
        with engine.begin() as conn:conn.execute(text('DROP SCHEMA IF EXISTS "'+schema+'" CASCADE'))
        engine.dispose()

@pytest.fixture
def app(tmp_path,remote_test_schema):
    if remote_test_schema:
        remote,options,schema,control=remote_test_schema
        config={'SQLALCHEMY_DATABASE_URI':remote,'SQLALCHEMY_ENGINE_OPTIONS':options}
    else:config={'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'test.db')}
    a=create_app({'TESTING':True,'STORAGE_BACKEND':'local',**config,'UPLOAD_DIR':str(tmp_path/'uploads'),'RATELIMIT_ENABLED':False})
    with a.app_context():
        if not remote_test_schema:db.create_all()
        try:
            db.session.add(User(email='admin@example.test',name='Admin',role='ADMIN',password_hash=generate_password_hash('test-password-123')));db.session.commit()
            yield a
        finally:
            db.session.remove()
            if remote_test_schema:
                # Clear ONLY this dedicated test schema between tests, in one query.
                quote=control.dialect.identifier_preparer.quote
                names=', '.join(quote(schema)+'.'+quote(n) for n in db.metadata.tables)
                with control.begin() as conn:conn.execute(text('TRUNCATE TABLE '+names+' RESTART IDENTITY CASCADE'))
            else:db.drop_all()
            db.engine.dispose()
@pytest.fixture
def client(app):return app.test_client()
def login(client,admin=False):
    token=client.get('/api/session').json['csrf']
    if admin:r=client.post('/api/auth/login',json={'email':'admin@example.test','password':'test-password-123'},headers={'X-CSRF-Token':token})
    else:return {'X-CSRF-Token':token}
    assert r.status_code in (200,201),r.json
    return {'X-CSRF-Token':r.json['csrf']}


def pytest_collection_modifyitems(items):
    # Diagnose the previously failed catalog tests first; retain every test.
    if os.getenv('PYQ_TEST_CATALOG_FIRST')=='1':
        items.sort(key=lambda item:item.path.name!='test_catalog.py')
