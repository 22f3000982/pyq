"""Use Supabase only after the migration runner's complete verification gate."""
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from backend.migration_service import target_identity
from backend.database_config import database_url
marker=ROOT/'migration-ready.json'
if marker.exists():
    ready=json.loads(marker.read_text());uri=database_url(os.getenv('DATABASE_URL',''),'')
    if not uri or ready.get('status')!='PASSED' or target_identity(uri)!=ready.get('target_identity'):
        raise SystemExit('Verified database does not match DATABASE_URL. Nothing started; check private configuration.')
    print('Starting with the verified PostgreSQL database.')
else:
    if os.getenv('RENDER','').lower()=='true':
        raise SystemExit('No verified PostgreSQL migration marker; refusing to start Render against SQLite.')
    local=ROOT/'instance/app.db'
    if not local.is_file():raise SystemExit('No verified PostgreSQL migration or prepared local copy exists. Run prepare_release.py first.')
    os.environ['DATABASE_URL']='sqlite:///'+local.as_posix()
    print('Migration not approved yet. Starting against the separate local SQLite copy.')
if os.getenv('STORAGE_BACKEND','local')=='r2':
    from backend.storage import identity
    proof=ROOT/'r2-ready.json'
    config={k:os.getenv(k,'pyq' if k=='R2_PREFIX' else '') for k in ('R2_ENDPOINT_URL','R2_BUCKET_NAME','R2_PDF_BUCKET_NAME','R2_IMAGE_BUCKET_NAME','R2_PREFIX')}
    ready=json.loads(proof.read_text()) if proof.exists() else {}
    if ready.get('status')!='PASSED' or ready.get('target_identity')!=identity(config):raise SystemExit('R2 target is not verified. Run FINISH-SETUP.cmd before starting with R2.')
print('Asset storage: '+os.getenv('STORAGE_BACKEND','local')+'.')
os.environ['CATALOG_AUTO_PROCESS']='false'
raise SystemExit(subprocess.call([sys.executable,'scripts/run_local.py'],cwd=ROOT))
