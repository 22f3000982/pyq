"""Back up local SQLite, migrate explicitly, test, then write an activation marker.
Never overwrite the original SQLite DB or PDFs. Credentials only in environment.
"""
import argparse,datetime,json,os,secrets,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from flask_migrate import upgrade
from backend import create_app
from backend.models import db
from backend.database_config import database_url,engine_options
from backend.migration_service import *


def run(source,uploads):
    source=Path(source).resolve();uploads=Path(uploads).resolve()
    if (ROOT/'migration-ready.json').exists():raise RuntimeError('An approved migration marker already exists. Refusing another import.')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    folder=ROOT/'migration-backups'/stamp;folder.mkdir(parents=True)
    report={'status':'RUNNING','stage':'backup','remote_connection_verified':False,'original_modified':False}
    secret_values=[v for k,v in os.environ.items() if v and (any(word in k.upper() for word in ('PASSWORD','SECRET','TOKEN','ACCESS_KEY','API_KEY')) or k=='DATABASE_URL')]
    target_uri=None
    def phase(name):
        report['stage']=name;print(name.replace('_',' ').capitalize()+'...',flush=True)
        (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    def command(args,cwd,env,label):
        phase(label)
        from backend.setup_runner import run_checked
        run_checked(args,cwd,env,label,folder/(label+'.txt'),secret_values)
    try:
        phase('backup')
        original_hash=backup_sqlite(source,folder/'original.sqlite3')
        report['original_sha256']=original_hash
        phase('validate_source')
        report['source_counts']=validate_source(folder/'original.sqlite3',uploads)
        phase('connection_check')
        raw=os.getenv('DATABASE_URL','')
        if not raw:raise RuntimeError('DATABASE_URL is not set. Supply it privately; no destination has been contacted.')
        target_uri=database_url(raw,'')
        if make_url(target_uri).get_backend_name()!='postgresql':raise RuntimeError('DATABASE_URL must point to PostgreSQL; no destination writes performed.')
        secret_values.extend([raw,target_uri,make_url(target_uri).password or ''])
        target_engine=create_engine(target_uri,**engine_options(target_uri))
        read_only_check(target_engine);report['remote_connection_verified']=True
        report['target_identity']=target_identity(target_uri)
        phase('inspect_existing_accounts')
        resume=verified_resume_snapshot(ROOT,original_hash,target_uri,target_engine,original_source=folder/'original.sqlite3',diagnostics=report.setdefault('resume_check',{}))
        report['resumed_verified_import']=bool(resume)
        if resume:print('Previous imported data matches its snapshot. Resuming verification; no data reimport.',flush=True)
        if not resume:
            report['archived_test_accounts']=archive_confirmed_fixture_accounts(target_engine)
            if report['archived_test_accounts']:print('Confirmed test accounts archived safely; real accounts are not changed.',flush=True)
            report['reused_empty_schema']=assert_empty_target(target_engine)
        phase('test_prerequisites')
        npm=npm_command()
        import pytest
        test_env=os.environ.copy();test_env['PYQ_TEST_DATABASE_URL']=target_uri;test_env['PYQ_TEST_CATALOG_FIRST']='1'
        test_env['SECRET_KEY']=secrets.token_hex(32);test_env['CATALOG_AUTO_PROCESS']='false';test_env['STORAGE_BACKEND']='local'
        lock_hash=digest_file(ROOT/'frontend/package-lock.json');installed=ROOT/'frontend/.installed-lock-sha256'
        if not installed.exists() or installed.read_text()!=lock_hash or not (ROOT/'frontend/node_modules/vitest').exists():
            command(npm+['ci','--include=dev','--no-audit','--no-fund'],ROOT/'frontend',test_env,'install_frontend_test_dependencies')
            installed.write_text(lock_hash)
        phase('prepare_source_copy')
        working=folder/'working.sqlite3';shutil.copy2(resume or folder/'original.sqlite3',working)
        report['stable_snapshot']=prepare_stable_migration_snapshot(working) if not resume else {'resumed':True}
        source_uri='sqlite:///'+working.as_posix()
        local=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':source_uri,'UPLOAD_DIR':str(uploads),'RATELIMIT_ENABLED':False,'STORAGE_BACKEND':'local'})
        with local.app_context():
            upgrade(directory=str(ROOT/'migrations'))
            from backend.engine import expire_all
            if not resume:expire_all()  # Never change a verified resume snapshot.
        source_engine=create_engine(source_uri)
        phase('apply_supabase_schema')
        remote=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':target_uri,'UPLOAD_DIR':str(uploads),'RATELIMIT_ENABLED':False,'STORAGE_BACKEND':'local'})
        with remote.app_context():upgrade(directory=str(ROOT/'migrations'))
        protect_backend_tables(target_engine)
        phase('copy_and_verify_rows')
        if resume:
            verify_source_rows(source_engine,target_engine)
            report['reconciliation']={'resumed':True}
        else:
            report['reconciliation']=reconcile_stable_rows(source_engine,target_engine)
        report['tables']={t.name:table_digest(source_engine,t) for t in db.metadata.sorted_tables}
        # Unit/integration fixtures use fresh isolated schemas in the same PG DB.
        # They must NEVER create/drop tables in the migrated public schema.
        command([sys.executable,'-u','-m','pytest','tests','-vv','-x','--tb=short','--durations=10'],ROOT,test_env,'backend_tests')
        command(npm+['exec','--','vitest','run'],ROOT/'frontend',test_env,'frontend_component_tests')
        command(npm+['test'],ROOT/'frontend',test_env,'frontend_unit_tests')
        command(npm+['run','build'],ROOT/'frontend',test_env,'frontend_build')
        phase('five_real_paper_acceptance')
        from scripts.migration_acceptance import five_paper_acceptance
        report['papers']=five_paper_acceptance(remote)
        phase('final_integrity_check')
        verify_source_rows(source_engine,target_engine)
        report['tables']={t.name:table_digest(source_engine,t) for t in db.metadata.sorted_tables}
        if digest_file(source)!=original_hash:raise RuntimeError('Original SQLite changed during migration. Activation blocked; stop the local app and investigate.')
        report['status']='PASSED';report['stage']='complete'
        (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        marker={'target_identity':target_identity(target_uri),'status':'PASSED','report':str(folder/'report.json'),'verified_at':stamp}
        (ROOT/'migration-ready.json').write_text(json.dumps(marker,indent=2),encoding='utf-8')
        print('Migration and all tests PASSED. Original SQLite/PDFs unchanged. Activation marker created.',flush=True)
        print('Report:',folder/'report.json')
    except Exception as exc:
        report['status']='FAILED';report['error']=safe_error(exc,secret_values)
        (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('STOPPED at '+report['stage']+': '+json.dumps(report['error']),flush=True)
        print('Original SQLite and PDFs were not modified by this tool. No activation marker created.')
        print('Backup and sanitized report:',folder)
        raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True,help='Existing SQLite app.db');parser.add_argument('--uploads',required=True,help='Existing local PDF/image directory')
    args=parser.parse_args();run(args.source,args.uploads)
