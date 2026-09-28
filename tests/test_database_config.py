import hashlib
from pathlib import Path
import pytest
from sqlalchemy.engine import make_url
from backend import create_app
from backend.database_config import database_url,engine_options

def test_database_url_driver_and_fallback():
    assert database_url('', 'sqlite:///existing.db')=='sqlite:///existing.db'
    raw='postgresql://postgres:PLACEHOLDER%40PASS@db.example.test:5432/postgres?sslmode=require'
    url=make_url(database_url(raw,''))
    assert url.drivername=='postgresql+psycopg'
    assert url.password=='PLACEHOLDER@PASS' and url.query['sslmode']=='require'
    assert engine_options(url)['pool_pre_ping'] is True
    with pytest.raises(ValueError,match='Invalid DATABASE_URL'):database_url('INVALID_SECRET_VALUE','')

def test_env_configuration_without_connecting(monkeypatch,tmp_path):
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://postgres:PLACEHOLDER@db.example.test:5432/postgres?sslmode=require')
    app=create_app({'TESTING':True,'UPLOAD_DIR':str(tmp_path),'RATELIMIT_ENABLED':False})
    assert app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql+psycopg://')
    assert app.config['SQLALCHEMY_ENGINE_OPTIONS']['connect_args']['connect_timeout']==10

def test_production_upload_directory_is_created_and_writable(monkeypatch,tmp_path):
    production_uploads=tmp_path/'data'/'uploads'
    monkeypatch.setenv('RENDER','true')
    monkeypatch.setenv('UPLOAD_DIR',str(production_uploads))
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'postgresql+psycopg://test:test@db.example.test/test','RATELIMIT_ENABLED':False,
                    'STORAGE_BACKEND':'r2','R2_ENDPOINT_URL':'https://test.r2.cloudflarestorage.com',
                    'R2_ACCESS_KEY_ID':'test-key','R2_SECRET_ACCESS_KEY':'test-secret',
                    'R2_PDF_BUCKET_NAME':'pyq-pdfs','R2_IMAGE_BUCKET_NAME':'pyq-images'})
    marker=production_uploads/'startup-check.tmp'
    marker.write_bytes(b'write check')
    assert app.config['UPLOAD_DIR']==str(production_uploads)
    assert marker.read_bytes()==b'write check'

def test_render_r2_configuration_fails_fast_without_separate_buckets(monkeypatch,tmp_path):
    monkeypatch.setenv('RENDER','true')
    with pytest.raises(RuntimeError,match='R2 production configuration'):
        create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'postgresql+psycopg://test:test@db.example.test/test','UPLOAD_DIR':str(tmp_path),'RATELIMIT_ENABLED':False,
                    'STORAGE_BACKEND':'r2','R2_PDF_BUCKET_NAME':'','R2_IMAGE_BUCKET_NAME':''})

def test_read_only_connection_check_and_secret_redaction(app,tmp_path,monkeypatch):
    from backend.models import db
    path=Path(db.engine.url.database) if db.engine.dialect.name=='sqlite' else None
    before=hashlib.sha256(path.read_bytes()).hexdigest() if path else None
    result=app.test_cli_runner().invoke(args=['check-db'])
    assert result.exit_code==0 and 'SELECT 1 passed' in result.output
    if path:assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    def fail():raise RuntimeError('postgresql://SECRET_MUST_NOT_APPEAR@host')
    monkeypatch.setattr(db.engine,'connect',fail)
    result=app.test_cli_runner().invoke(args=['check-db'])
    assert result.exit_code!=0 and 'SECRET_MUST_NOT_APPEAR' not in result.output
