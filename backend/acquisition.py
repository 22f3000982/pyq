"""Public-source acquisition with bounded downloads and an explicit domain policy.
No credentials, permission bypasses, login scraping or hidden Drive APIs.
"""
import hashlib,re,time,uuid
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import urlparse,urljoin,parse_qs
from pathlib import Path
import requests
from flask import current_app
from sqlalchemy import func,update
from sqlalchemy.exc import IntegrityError
from .models import db,Paper,Question,IngestionBatch,IngestionFile,User

ALLOWED={'drive.google.com','drive.usercontent.google.com','drive.googleusercontent.com','docs.google.com','google.com','www.google.com'}

def safe_url(url):
    u=urlparse(url)
    if u.scheme not in ('http','https') or u.username or u.password or u.port not in (None,80,443):raise ValueError('Unsupported source URL')
    if u.hostname not in ALLOWED and not (u.hostname or '').endswith('.googleusercontent.com'):
        raise ValueError('Source host is not in the configured download allowlist: '+str(u.hostname))
    return url

def drive_file_id(url):
    u=urlparse(url);query=parse_qs(u.query)
    match=re.search(r'/file/d/([\w-]+)',u.path)
    if u.hostname=='drive.google.com' and (match or query.get('id')):
        return match[1] if match else query['id'][0]
    return None

def download_url(url):
    safe_url(url);u=urlparse(url);query=parse_qs(u.query)
    if u.hostname in ('google.com','www.google.com') and u.path=='/url' and query.get('q'):
        url=query['q'][0];safe_url(url);u=urlparse(url)
    match=re.search(r'/file/d/([\w-]+)',u.path)
    if u.hostname=='drive.google.com' and (match or query.get('id')):
        fileid=match[1] if match else query['id'][0]
        return 'https://drive.google.com/uc?export=download&id='+fileid
    match=re.search(r'/document/(?:u/\d+/)?d/([\w-]+)',u.path)
    if u.hostname=='docs.google.com' and match and match[1]!='e':
        return 'https://docs.google.com/document/d/'+match[1]+'/export?format=pdf'
    return url

def fetch_pdf(url,destination,max_bytes=20*1024*1024):
    file_id=drive_file_id(url)
    if file_id:
        from .google_drive import credential,download_file
        if credential() is not None:
            return download_file(file_id,destination,max_bytes)
    url=download_url(url)
    session=requests.Session();session.trust_env=True
    for _ in range(8):
        safe_url(url)
        response=session.get(url,stream=True,timeout=(10,35),allow_redirects=False)
        if response.status_code in (301,302,303,307,308):
            target=urljoin(url,response.headers.get('Location',''));response.close();url=target;continue
        if response.status_code!=200:
            code=response.status_code;response.close();raise ValueError(f'Source HTTP {code}; permission, expiry or service restriction')
        length=int(response.headers.get('Content-Length','0') or 0)
        if length>max_bytes:response.close();raise ValueError('Source exceeds download byte limit')
        size=0;sha=hashlib.sha256();start=time.monotonic();first=True
        try:
            with open(destination,'wb') as out:
                for block in response.iter_content(65536):
                    if not block:continue
                    if first:
                        first=False
                        if not block.startswith(b'%PDF-'):
                            lower=block[:10000].lower()
                            reason='Source returned HTML/non-PDF content'
                            if b'accounts.google' in lower or b'sign in' in lower:reason+=' (sign-in or permission required)'
                            elif b'quota' in lower:reason+=' (download quota)'
                            elif b'virus' in lower:reason+=' (interactive download confirmation required)'
                            raise ValueError(reason)
                    size+=len(block)
                    if size>max_bytes:raise ValueError('Source exceeds download byte limit')
                    if time.monotonic()-start>100:raise ValueError('Source download time limit exceeded')
                    sha.update(block);out.write(block)
            if size==0:raise ValueError('Source returned an empty file')
            return {'hash':sha.hexdigest(),'size':size,'resolved_url':url}
        except Exception:
            Path(destination).unlink(missing_ok=True);raise
        finally:response.close();session.close()
    raise ValueError('Too many source redirects')

def event(f,stage,message):
    f.events=(f.events or [])+[{'time':time.time(),'stage':stage,'message':str(message)[:1600]}]

def queue_catalog(user_id=None,retry=False,limit=None,paper_ids=None,force_paper_ids=None):
    admin=db.session.get(User,user_id) if user_id else User.query.filter_by(role='ADMIN').first()
    # Queue creation is also allowed for the CLI before creating a login account.
    if not admin:
        from werkzeug.security import generate_password_hash
        admin=User.query.filter_by(email='ingestion-service@internal.invalid').first()
        if not admin:
            admin=User(email='ingestion-service@internal.invalid',name='Ingestion service',role='SYSTEM',active=False,password_hash=generate_password_hash(uuid.uuid4().hex));db.session.add(admin);db.session.flush()
    batch=IngestionBatch(user_id=admin.id)
    db.session.add(batch);db.session.flush();count=0
    force_paper_ids=set(force_paper_ids or [])
    query=Paper.query.filter(Paper.source_url.isnot(None),Paper.status!='ARCHIVED').order_by(Paper.id)
    if paper_ids is not None:query=query.filter(Paper.id.in_(paper_ids))
    papers=query.all()
    # One grouped lookup replaces one remote PostgreSQL query per paper. This is
    # important when the first manual sync selects hundreds of catalog entries.
    ids=[p.id for p in papers]
    latest={}
    if ids:
        latest_ids=db.session.query(func.max(IngestionFile.id)).filter(IngestionFile.paper_id.in_(ids)).group_by(IngestionFile.paper_id)
        latest={f.paper_id:f for f in IngestionFile.query.filter(IngestionFile.id.in_(latest_ids)).all()}
    selected=0
    for p in papers:
        if limit is not None and selected>=limit:break
        previous=latest.get(p.id)
        forced=p.id in force_paper_ids
        if forced:
            if previous and previous.status in ('QUEUED','FETCHING','PROCESSING','FETCH_QUEUED'):continue
            # A changed source must become a new ingestion record. Never mutate an
            # AVAILABLE historical record because attempts may reference its questions.
            f=IngestionFile(batch_id=batch.id,paper_id=p.id,filename=p.name,source_url=p.source_url,status='FETCH_QUEUED')
            db.session.add(f);count+=1;selected+=1;continue
        if previous and previous.status in ('AVAILABLE','PARTIAL','DUPLICATE','QUEUED','FETCHING','PROCESSING','FETCH_QUEUED'):continue
        if previous and previous.status in ('PROCESSING_FAILED','EXTRACTION_FAILED') and not retry:continue
        if previous and previous.status=='PAUSED':continue
        if previous and previous.path:
            previous.status='QUEUED';previous.error=None;previous.batch_id=batch.id;previous.source_url=p.source_url;count+=1
        else:
            f=IngestionFile(batch_id=batch.id,paper_id=p.id,filename=p.name,source_url=p.source_url,status='FETCH_QUEUED');db.session.add(f);count+=1
        selected+=1
    db.session.commit();return batch.id,count


def download_one(file_id):
    """Atomically acquire and download one queued catalog source."""
    record=db.session.get(IngestionFile,file_id)
    if record is None:return False
    if record.status!='FETCH_QUEUED':return record.status in ('QUEUED','DUPLICATE','AVAILABLE','PARTIAL')
    claimed=db.session.execute(update(IngestionFile).where(
        IngestionFile.id==file_id,IngestionFile.status=='FETCH_QUEUED'
    ).values(status='FETCHING',started_at=time.time(),error=None)).rowcount
    db.session.commit()
    if not claimed:return False
    record=db.session.get(IngestionFile,file_id);paper=db.session.get(Paper,record.paper_id)
    temp=Path(current_app.config['UPLOAD_DIR'])/('fetch-'+uuid.uuid4().hex+'.tmp')
    try:
        result=fetch_pdf(record.source_url,temp,current_app.config['MAX_UPLOAD_SIZE'])
    except Exception as exc:
        temp.unlink(missing_ok=True);db.session.rollback()
        record=db.session.get(IngestionFile,file_id);paper=db.session.get(Paper,record.paper_id)
        record.status='PROCESSING_FAILED';record.error=str(exc)[:1500];record.finished_at=time.time()
        if paper.status!='ARCHIVED':paper.status='PROCESSING_FAILED'
        event(record,'ACQUISITION_FAILED',record.error);db.session.commit()
        from .ingestion import update_batch
        update_batch(record.batch_id)
        return False
    old=IngestionFile.query.filter(IngestionFile.file_hash==result['hash'],IngestionFile.id!=file_id).first()
    if old:
        temp.unlink(missing_ok=True);record.duplicate_of_id=old.id;record.status='DUPLICATE';record.path=old.path
        canonical=db.session.get(Paper,old.paper_id)
        paper.canonical_paper_id=old.paper_id if old.paper_id!=paper.id else None
        if canonical and canonical.status in ('AVAILABLE','PARTIALLY_AVAILABLE'):paper.status=canonical.status
        elif old.paper_id==paper.id and Question.query.filter_by(paper_id=paper.id,status='AVAILABLE').first():paper.status='AVAILABLE'
        event(record,'DEDUPLICATED',f'Identical PDF content to import {old.id}, paper {old.paper_id}')
        record.finished_at=time.time();db.session.commit()
        from .ingestion import update_batch
        update_batch(record.batch_id)
        return True
    path=result['hash']+'.pdf';temp.replace(Path(current_app.config['UPLOAD_DIR'])/path)
    record.path=path;record.file_hash=result['hash']
    try:
        from .storage import publish
        publish(path);record.status='QUEUED';event(record,'DOWNLOADED',f"{result['size']} bytes; SHA-256 {result['hash']}")
    except Exception as exc:
        from .storage import StorageError
        if not isinstance(exc,StorageError):raise
        record.status='PROCESSING_FAILED';record.error=str(exc);record.finished_at=time.time()
        if paper.status!='ARCHIVED':paper.status='PROCESSING_FAILED'
        event(record,'STORAGE_FAILED',record.error)
    db.session.commit()
    if record.status=='PROCESSING_FAILED':
        from .ingestion import update_batch
        update_batch(record.batch_id)
        return False
    return True

def download_pending(app,workers=4,paper_ids=None,limit=None):
    with app.app_context():
        query=IngestionFile.query.join(Paper,Paper.id==IngestionFile.paper_id).filter(IngestionFile.status=='FETCH_QUEUED',Paper.status!='ARCHIVED')
        if paper_ids is not None:query=query.filter(IngestionFile.paper_id.in_(paper_ids))
        query=query.order_by(IngestionFile.id)
        if limit is not None:query=query.limit(limit)
        jobs=[(f.id,f.source_url) for f in query]
        directory=Path(app.config['UPLOAD_DIR']);max_bytes=app.config['MAX_UPLOAD_SIZE']
    def download(job):
        id,url=job;temp=directory/('fetch-'+uuid.uuid4().hex+'.tmp')
        try:return id,temp,fetch_pdf(url,temp,max_bytes),None
        except Exception as e:return id,temp,None,str(e)[:1500]
    # Only the owner thread writes SQLite; downloads are independent bounded tasks.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(download,j) for j in jobs]
        for n,future in enumerate(as_completed(futures),1):
            id,temp,result,error=future.result()
            with app.app_context():
                f=db.session.get(IngestionFile,id);p=db.session.get(Paper,f.paper_id);f.started_at=time.time()
                if error:
                    f.status='PROCESSING_FAILED';f.error=error;f.finished_at=time.time();p.status='PROCESSING_FAILED';event(f,'ACQUISITION_FAILED',error)
                else:
                    old=IngestionFile.query.filter_by(file_hash=result['hash']).first()
                    if old:
                        temp.unlink(missing_ok=True);f.duplicate_of_id=old.id;f.status='DUPLICATE';f.path=old.path
                        canonical=db.session.get(Paper,old.paper_id)
                        p.canonical_paper_id=old.paper_id if old.paper_id!=p.id else None
                        if canonical and canonical.status in ('AVAILABLE','PARTIALLY_AVAILABLE'):
                            p.status=canonical.status
                        elif old.paper_id==p.id and Question.query.filter_by(paper_id=p.id,status='AVAILABLE').first():
                            p.status='AVAILABLE'
                        event(f,'DEDUPLICATED',f'Identical PDF content to import {old.id}, paper {old.paper_id}');f.finished_at=time.time()
                    else:
                        path=result['hash']+'.pdf';temp.replace(directory/path);f.path=path;f.file_hash=result['hash']
                        try:
                            from .storage import publish
                            publish(path);f.status='QUEUED';event(f,'DOWNLOADED',f"{result['size']} bytes; SHA-256 {result['hash']}")
                        except Exception as exc:
                            from .storage import StorageError
                            if not isinstance(exc,StorageError):raise
                            f.status='PROCESSING_FAILED';f.error=str(exc);f.finished_at=time.time();p.status='PROCESSING_FAILED';event(f,'STORAGE_FAILED',f.error)
                db.session.commit()
            if n%20==0 or n==len(jobs):print(f'Downloaded/attempted {n}/{len(jobs)}',flush=True)
    return len(jobs)
