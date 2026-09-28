"""Idempotently copy/verify local assets in private R2; never delete originals."""
import json,os,sys,time,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv,set_key
load_dotenv(ROOT/'.env')
from backend import create_app
from backend.storage import configured,identity,publish,StorageError,authenticate_or_convert_token


def run():
    app=create_app({'STORAGE_BACKEND':'r2'})
    if not configured(app.config) or not (app.config.get('R2_PDF_BUCKET_NAME') and app.config.get('R2_IMAGE_BUCKET_NAME')):
        print('R2 PENDING: set R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_PDF_BUCKET_NAME and R2_IMAGE_BUCKET_NAME privately in Final-App/.env. Database readiness is unchanged.')
        return 2
    folder=ROOT/'storage-reports';folder.mkdir(exist_ok=True)
    report={'status':'RUNNING','uploaded':0,'already_present':0,'verified':0,'originals_deleted':False}
    destination=folder/(str(time.time_ns())+'.json')
    try:
        with app.app_context():
            if authenticate_or_convert_token():
                private_backup=ROOT/'update-backups'/('r2-private-'+str(time.time_ns())+'.env')
                private_backup.parent.mkdir(parents=True,exist_ok=True)
                if (ROOT/'.env').is_file():
                    shutil.copy2(ROOT/'.env',private_backup)
                    private_backup.chmod(0o600)
                set_key(str(ROOT/'.env'),'R2_SECRET_ACCESS_KEY',app.config['R2_SECRET_ACCESS_KEY'])
                print('R2 credentials repaired using documented API-token conversion; authenticated successfully. No secrets displayed.',flush=True)
            root=Path(app.config['UPLOAD_DIR']).resolve()
            files=sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ('.pdf','.png','.jpg','.jpeg','.webp','.gif'))
            if not files:raise StorageError('No local PDF/image assets found; R2 was not enabled.')
            for i,p in enumerate(files,1):
                result=publish(p.relative_to(root).as_posix(),verify=True)
                report[result]+=1;report['verified']+=1
                if i%20==0 or i==len(files):print(f'R2 assets verified: {i}/{len(files)}',flush=True)
                destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
            report['status']='PASSED';report['target_identity']=identity(app.config)
        destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
        (ROOT/'r2-ready.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        set_key(str(ROOT/'.env'),'STORAGE_BACKEND','r2',quote_mode='never')
        print('R2 PASSED: every asset read back and checksum verified; local originals preserved. R2 enabled for future uploads and asset delivery.')
        return 0
    except Exception as exc:
        report['status']='FAILED';report['error']=str(exc) if isinstance(exc,StorageError) else type(exc).__name__+' during asset sync'
        destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('R2 STOPPED: '+report['error']);print('Sanitized report:',destination)
        return 1

if __name__=='__main__':raise SystemExit(run())
