"""Publish missing source assets after read-only PostgreSQL and R2 preflight.

Uses the existing storage layer, never changes credentials/configuration, never
writes database rows, and never reparses PDFs or overwrites conflicting objects.
"""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend import create_app
from backend.models import db,QuestionImage,IngestionFile
from backend.storage import configured,identity,publish,remote_head,check_access,StorageError,local_path
from sqlalchemy import text


def asset_manifest():
    if db.engine.dialect.name!='postgresql':
        raise StorageError('Asset sync requires the current PostgreSQL database. SQLite is not a production fallback.')
    with db.engine.connect() as connection:
        connection.execute(text('SET TRANSACTION READ ONLY'))
        assert connection.execute(text('SELECT 1')).scalar_one()==1
        names={row[0] for row in connection.execute(db.select(QuestionImage.path))}
        names.update(row[0] for row in connection.execute(db.select(IngestionFile.path).where(IngestionFile.path.isnot(None))))
        connection.rollback()
    return sorted(names)


def sync_assets(names,dry_run=False):
    check_access()  # Both configured buckets must be readable before any upload.
    missing=[];present=[];unavailable=[]
    for name in names:
        if remote_head(name) is None:
            missing.append(name)
            if not local_path(name).is_file():unavailable.append(name)
        else:present.append(name)
    result={'status':'DRY_RUN' if dry_run else 'PREFLIGHT','referenced':len(names),'existing':len(present),'missing':len(missing),'missing_local_assets':unavailable,'uploaded':0,'already_present':0,'verified':0,'originals_deleted':False}
    if unavailable:
        result['status']='LOCAL_ASSETS_MISSING';return result
    if dry_run:return result
    # publish() checks immutable SHA-256 metadata and uses a conditional PUT;
    # existing objects are read back, but are never uploaded again.
    for name in names:
        if local_path(name).is_file():
            state=publish(name,verify=True);result[state]+=1;result['verified']+=1
        else:
            # A remote-only asset is valid: verify its stored checksum directly.
            from backend.storage import remote_bytes
            remote_bytes(name);result['already_present']+=1;result['verified']+=1
        if result['verified']%20==0 or result['verified']==len(names):
            print(f"R2 assets verified: {result['verified']}/{len(names)}",flush=True)
    result['status']='PASSED';return result


def run(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,help='Existing uploads folder containing PDFs and extracted images')
    parser.add_argument('--dry-run',action='store_true',help='Read-only inventory; do not upload')
    parser.add_argument('--report',type=Path,help='Optional sanitized local JSON report')
    args=parser.parse_args(argv)
    try:
        config={'STORAGE_BACKEND':'r2'}
        if args.source_dir:config['UPLOAD_DIR']=str(args.source_dir.resolve())
        app=create_app(config)
        if not configured(app.config) or not all(app.config.get(k) for k in ('R2_PDF_BUCKET_NAME','R2_IMAGE_BUCKET_NAME')):
            raise StorageError('Configure the private R2 endpoint, S3 credentials and separate PDF/image bucket names.')
        with app.app_context():
            names=asset_manifest()
            if not names:raise StorageError('Current PostgreSQL database has no source asset references; refusing an unrelated folder upload.')
            report=sync_assets(names,args.dry_run)
            report['target_identity']=identity(app.config)
    except Exception as exc:
        report={'status':'FAILED','error':str(exc) if isinstance(exc,StorageError) else type(exc).__name__+' during asset sync; check private configuration/connectivity','originals_deleted':False}
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return 0 if report['status'] in ('PASSED','DRY_RUN') else 1

if __name__=='__main__':raise SystemExit(run())
