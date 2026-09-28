"""One resumable setup entry point: database first, then durable R2 assets."""
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')

def main():
    marker=ROOT/'migration-ready.json'
    if not marker.exists():
        result=subprocess.call([sys.executable,'scripts/migrate_to_supabase.py','--source','instance/app.db','--uploads','uploads'],cwd=ROOT)
        if result:return result
    else:
        from backend.database_config import database_url,engine_options
        from backend.migration_service import target_identity,read_only_check
        from sqlalchemy import create_engine
        try:
            uri=database_url(os.getenv('DATABASE_URL',''),'');saved=json.loads(marker.read_text())
            if saved.get('status')!='PASSED' or saved.get('target_identity')!=target_identity(uri):raise RuntimeError('Verified migration target does not match.')
            engine=create_engine(uri,**engine_options(uri));read_only_check(engine);engine.dispose()
            print('Existing verified database retained; no repeat data import.',flush=True)
        except Exception as exc:
            print('STOPPED: '+type(exc).__name__+' checking the verified database. Check private configuration/network. No import performed.')
            return 1
    result=subprocess.call([sys.executable,'scripts/sync_r2.py'],cwd=ROOT)
    if result==0:print('DATABASE AND R2 READY. Start this same Final-App folder with START.cmd.',flush=True)
    elif result==2:print('Database setup passed. R2 needs its private endpoint, credential pair, and separate PDF/image bucket names; rerun FINISH-SETUP.cmd after saving them.',flush=True)
    return result

if __name__=='__main__':raise SystemExit(main())
