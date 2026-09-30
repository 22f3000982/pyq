"""Private local/R2 assets. Database paths stay stable; no bucket secrets in APIs."""
import hashlib,io,mimetypes,os,re,uuid
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit,quote
from flask import current_app,send_file,abort
from .performance import span,count

class StorageError(RuntimeError):pass

def configure_delivery(app):
    mode=app.config.get('IMAGE_DELIVERY','proxy')
    if mode not in ('proxy','signed','cdn'):raise ValueError('IMAGE_DELIVERY must be proxy, signed or cdn')
    app.extensions['image_cdn_manifest']={}
    origin=None
    if mode=='cdn':
        import json
        u=urlsplit(app.config.get('IMAGE_CDN_BASE_URL',''))
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
            raise ValueError('IMAGE_CDN_BASE_URL must be an HTTPS origin')
        origin=u.scheme+'://'+u.netloc
        manifest=json.loads(Path(app.config['IMAGE_CDN_MANIFEST']).read_text())
        # Explicit allowlist: never make all source PDF/page assets public.
        if not isinstance(manifest,dict) or any(not isinstance(v,str) or not re.fullmatch(r'public-questions/[a-f0-9]{64}\.(png|webp|jpg)',v) for v in manifest.values()):
            raise ValueError('CDN manifest requires content-hashed question image keys')
        app.extensions['image_cdn_manifest']=manifest
    elif mode=='signed':
        u=urlsplit(app.config.get('R2_ENDPOINT_URL',''))
        if u.scheme!='https' or not u.hostname or not u.hostname.endswith('.r2.cloudflarestorage.com') or u.username or u.password:
            raise ValueError('Signed image delivery requires a valid R2 endpoint')
        # Path-style signing keeps the CSP allowlist scoped to one account endpoint.
        origin=u.scheme+'://'+u.netloc
    app.extensions['image_origin']=origin

def image_url(name,image_id,expires=None):
    if enabled():
        mode=current_app.config.get('IMAGE_DELIVERY','proxy')
        if mode=='cdn':
            key=current_app.extensions['image_cdn_manifest'].get(name)
            if key:return current_app.extensions['image_origin']+'/'+quote(key,safe='/')
        if mode=='signed':
            return private_asset_url(name,image_id,expires=expires or 600)
    return '/api/images/'+str(image_id)

def configured(config):
    credentials=all(config.get(k) for k in ('R2_ENDPOINT_URL','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY'))
    separate=bool(config.get('R2_PDF_BUCKET_NAME') and config.get('R2_IMAGE_BUCKET_NAME'))
    legacy=bool(config.get('R2_BUCKET_NAME'))
    return credentials and (separate or legacy)

def identity(config):
    return hashlib.sha256('|'.join(str(config.get(k,'')) for k in ('R2_ENDPOINT_URL','R2_PDF_BUCKET_NAME','R2_IMAGE_BUCKET_NAME','R2_BUCKET_NAME','R2_PREFIX')).encode()).hexdigest()

def local_path(name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or '\x00' in name:raise StorageError('Invalid asset path')
    parts=PurePosixPath(name)
    if parts.is_absolute() or '..' in parts.parts or any(p.startswith('.') for p in parts.parts):raise StorageError('Invalid asset path')
    root=Path(current_app.config['UPLOAD_DIR']).resolve();path=(root/name).resolve()
    if not path.is_relative_to(root):raise StorageError('Invalid asset path')
    return path

def enabled():return current_app.config.get('STORAGE_BACKEND','local')=='r2'

def client():
    if '_r2_client' in current_app.extensions:return current_app.extensions['_r2_client']
    config=current_app.config
    if not configured(config):raise StorageError('R2 configuration is incomplete. Set the endpoint, access keys and both PDF/image bucket names privately.')
    u=urlsplit(config['R2_ENDPOINT_URL'])
    if u.scheme!='https' or not u.hostname or not u.hostname.endswith('.r2.cloudflarestorage.com') or u.username or u.password or u.query or u.fragment:
        raise StorageError('R2 endpoint must be the HTTPS S3 API endpoint from Cloudflare.')
    import boto3
    from botocore.config import Config
    # The checksum kwargs only exist in newer botocore releases. They are not
    # needed for these immutable R2 operations and made the existing pinned
    # client fail before it could make a request on older Windows installs.
    c=boto3.client('s3',endpoint_url=config['R2_ENDPOINT_URL'],region_name='auto',aws_access_key_id=config['R2_ACCESS_KEY_ID'],aws_secret_access_key=config['R2_SECRET_ACCESS_KEY'],config=Config(signature_version='s3v4',s3={'addressing_style':'path'},connect_timeout=10,read_timeout=30,retries={'mode':'standard','max_attempts':3}))
    current_app.extensions['_r2_client']=c;return c

def object_args(name):
    local_path(name)
    prefix=current_app.config.get('R2_PREFIX','pyq').strip('/')
    if '..' in prefix.split('/') or '\\' in prefix:raise StorageError('Invalid R2 prefix')
    suffix=Path(name).suffix.lower()
    image_bucket=current_app.config.get('R2_IMAGE_BUCKET_NAME') or current_app.config.get('R2_BUCKET_NAME')
    pdf_bucket=current_app.config.get('R2_PDF_BUCKET_NAME') or current_app.config.get('R2_BUCKET_NAME')
    bucket=image_bucket if suffix in ('.png','.jpg','.jpeg','.webp','.gif') else pdf_bucket
    return {'Bucket':bucket,'Key':(prefix+'/' if prefix else '')+name}

def failure(exc,operation):
    # Never expose exception URLs, signed headers, keys, request bodies or tokens.
    code=(getattr(exc,'response',None) or {}).get('Error',{}).get('Code',type(exc).__name__)
    code=re.sub(r'[^A-Za-z0-9_-]','',str(code))[:80]
    if code=='SignatureDoesNotMatch':
        return StorageError('R2 authentication failed (SignatureDoesNotMatch). Set R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY from the SAME Cloudflare R2 S3 credentials pair in your private .env. Use Secret Access Key, not the API token value. Local files are preserved.')
    if code in ('AccessDenied','403'):
        return StorageError('R2 access denied ('+code+'). Check the selected bucket, matching S3 credentials and Object Read & Write permission. Local files are preserved.')
    return StorageError('R2 '+operation+' failed ('+code+'). Check private configuration/network; local files are preserved.')

def check_access():
    """Read-only authenticated check; XML errors identify mismatched credentials."""
    try:
        buckets=[]
        for key in ('R2_PDF_BUCKET_NAME','R2_IMAGE_BUCKET_NAME','R2_BUCKET_NAME'):
            value=current_app.config.get(key)
            if value and value not in buckets:buckets.append(value)
        for bucket in buckets:client().list_objects_v2(Bucket=bucket,MaxKeys=1)
    except StorageError:raise
    except Exception as exc:raise failure(exc,'authentication') from None

def authenticate_or_convert_token():
    """Compatibility entry point: authentication never rewrites private credentials."""
    check_access()
    return False

def remote_head(name):
    try:return client().head_object(**object_args(name))
    except StorageError:raise
    except Exception as exc:
        code=str((getattr(exc,'response',None) or {}).get('Error',{}).get('Code',''))
        if code in ('404','NoSuchKey','NotFound'):return None
        raise failure(exc,'metadata check') from None

def remote_bytes(name):
    try:
        obj=client().get_object(**object_args(name));body=obj['Body']
        try:data=body.read()
        finally:body.close()
        digest=obj.get('Metadata',{}).get('sha256')
        if not digest or hashlib.sha256(data).hexdigest()!=digest:raise StorageError('R2 asset checksum mismatch or missing checksum metadata.')
        return data
    except StorageError:raise
    except Exception as exc:raise failure(exc,'download') from None

def publish(name,verify=False,_retry=0):
    path=local_path(name)
    if not path.is_file():raise StorageError('Required local asset is missing.')
    if not enabled():return 'local'
    data=path.read_bytes();digest=hashlib.sha256(data).hexdigest();head=remote_head(name)
    if head:
        if head.get('Metadata',{}).get('sha256')!=digest or head.get('ContentLength')!=len(data):
            raise StorageError('R2 object conflicts with the local asset. No remote object was overwritten.')
        result='already_present'
    else:
        put_args=dict(object_args(name),Body=data,ContentType=mimetypes.guess_type(name)[0] or 'application/octet-stream',Metadata={'sha256':digest})
        # Older botocore service models reject IfNoneMatch before sending the
        # request. Keep the conditional header when the installed SDK supports
        # it; otherwise the preflight HEAD plus immutable post-write check is
        # the compatible fallback.
        sdk=client()
        model=getattr(getattr(sdk,'meta',None),'service_model',None)
        supports_conditional=True if model is None else 'IfNoneMatch' in model.operation_model('PutObject').input_shape.members
        if supports_conditional:
            put_args['IfNoneMatch']='*'
        try:sdk.put_object(**put_args)
        except Exception as exc:
            # A concurrent upload may have stored this same immutable asset.
            if _retry<2 and str((getattr(exc,'response',None) or {}).get('Error',{}).get('Code','')) in ('PreconditionFailed','412'):
                return publish(name,verify=verify,_retry=_retry+1)
            raise failure(exc,'upload') from None
        head=remote_head(name)
        if not head or head.get('ContentLength')!=len(data) or head.get('Metadata',{}).get('sha256')!=digest:raise StorageError('R2 upload verification failed; local file preserved.')
        result='uploaded'
    if verify and hashlib.sha256(remote_bytes(name)).hexdigest()!=digest:raise StorageError('R2 readback verification failed.')
    return result

def ensure_local(name):
    path=local_path(name)
    if path.is_file():
        count('asset_hit');return path
    count('asset_miss')
    if not enabled():raise FileNotFoundError('Asset not found')
    with span('r2_download'):data=remote_bytes(name)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with span('disk_write'):
            temporary.write_bytes(data);os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
    return path

def write_asset(name,data):
    path=local_path(name);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with span('disk_write'):
            temporary.write_bytes(data);os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
    publish(name)
    return path

def send_asset(name,**kwargs):
    with span('send_asset'):
        try:
            with span('ensure_local'):path=ensure_local(name)
        except FileNotFoundError:abort(404)
        return send_file(path,**kwargs)

def private_asset_url(name,image_id=None,expires=600):
    if enabled():
        try:
            # SigV4 presigned GET URLs support at most seven days. Clamp caller
            # values so a long practice session never creates an invalid URL.
            expires=max(60,min(int(expires),604799))
            return client().generate_presigned_url('get_object',Params=object_args(name),ExpiresIn=expires)
        except StorageError:raise
        except Exception as exc:raise failure(exc,'signed URL generation') from None
    return '/api/images/'+str(image_id) if image_id is not None else None
