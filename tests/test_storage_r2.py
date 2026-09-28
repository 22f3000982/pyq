import hashlib,io
from pathlib import Path
import pytest
from botocore.exceptions import ClientError
from backend.storage import write_asset,publish,ensure_local,StorageError,remote_bytes

class MemoryR2:
    def __init__(self):self.objects={};self.puts=0
    def head_object(self,Bucket,Key):
        if Key not in self.objects:raise ClientError({'Error':{'Code':'404'}},'HeadObject')
        data,meta=self.objects[Key];return {'ContentLength':len(data),'Metadata':meta}
    def put_object(self,Bucket,Key,Body,Metadata,**kwargs):
        assert kwargs['IfNoneMatch']=='*';self.objects[Key]=(bytes(Body),Metadata);self.puts+=1
    def get_object(self,Bucket,Key):
        if Key not in self.objects:raise ClientError({'Error':{'Code':'NoSuchKey'}},'GetObject')
        data,meta=self.objects[Key];return {'Body':io.BytesIO(data),'Metadata':meta}

@pytest.fixture
def remote(app):
    app.config.update(STORAGE_BACKEND='r2',R2_ENDPOINT_URL='https://test.r2.cloudflarestorage.com',R2_ACCESS_KEY_ID='test-key',R2_SECRET_ACCESS_KEY='test-secret',R2_BUCKET_NAME='test',R2_PREFIX='pyq')
    fake=MemoryR2();app.extensions['_r2_client']=fake;return fake

def test_r2_persistence_cache_recovery_dedup_and_integrity(app,remote):
    path=write_asset('source.pdf',b'%PDF-source bytes')
    assert publish('source.pdf',verify=True)=='already_present' and remote.puts==1
    path.unlink();assert ensure_local('source.pdf').read_bytes()==b'%PDF-source bytes'
    path.write_bytes(b'different')
    with pytest.raises(StorageError,match='conflicts'):publish('source.pdf')
    assert remote.puts==1
    path.unlink();_,meta=remote.objects['pyq/source.pdf'];remote.objects['pyq/source.pdf']=(b'corrupt',meta)
    with pytest.raises(StorageError,match='checksum'):ensure_local('source.pdf')
    assert not path.exists()

@pytest.mark.parametrize('name',['../.env','/secret','C:\\secret','x/../../secret','.env'])
def test_storage_rejects_path_escape(app,remote,name):
    with pytest.raises(StorageError,match='path'):write_asset(name,b'x')
    assert not remote.objects

def test_local_backend_works_without_r2(app):
    p=write_asset('plain.pdf',b'%PDF-local');assert ensure_local('plain.pdf')==p

def test_real_upload_ingestion_then_cold_cache_student_assets(app,client,remote):
    from test_automatic import ingest_real
    from conftest import login
    from backend.models import Question,QuestionImage
    p,f=ingest_real(app)
    assert f.status=='AVAILABLE',f.error
    images=QuestionImage.query.all();assert images
    assert 'pyq/'+f.path in remote.objects
    for image in images:assert 'pyq/'+image.path in remote.objects
    root=Path(app.config['UPLOAD_DIR']);(root/f.path).unlink()
    for image in images:(root/image.path).unlink(missing_ok=True)
    assert client.get('/api/images/'+str(images[0].id)).status_code==401
    login(client)
    assert client.get('/api/images/'+str(images[0].id)).status_code==200
    assert client.get('/api/papers/'+str(p.id)+'/source').data.startswith(b'%PDF-')
    assert Question.query.filter_by(status='AVAILABLE').count()==20

def test_storage_failure_does_not_leak_secrets(app,remote):
    def fail(**kwargs):raise ClientError({'Error':{'Code':'AccessDenied','Message':'test-secret https://signed-url'}},'PutObject')
    remote.put_object=fail
    with pytest.raises(StorageError) as exc:write_asset('failed.pdf',b'%PDF-preserve me')
    assert 'test-secret' not in str(exc.value) and 'signed-url' not in str(exc.value)
    assert (Path(app.config['UPLOAD_DIR'])/'failed.pdf').read_bytes()==b'%PDF-preserve me'


def test_real_boto3_request_contract_with_stubbed_transport(app):
    from botocore.stub import Stubber
    from backend.storage import client
    app.config.update(STORAGE_BACKEND='r2',R2_ENDPOINT_URL='https://test.r2.cloudflarestorage.com',R2_ACCESS_KEY_ID='test-key',R2_SECRET_ACCESS_KEY='test-secret',R2_BUCKET_NAME='test',R2_PREFIX='pyq')
    sdk=client();data=b'%PDF-sdk';digest=hashlib.sha256(data).hexdigest();args={'Bucket':'test','Key':'pyq/sdk.pdf'}
    with Stubber(sdk) as stub:
        stub.add_client_error('head_object',service_error_code='404',http_status_code=404,expected_params=args)
        put_args=dict(args,Body=data,ContentType='application/pdf',Metadata={'sha256':digest})
        if 'IfNoneMatch' in sdk.meta.service_model.operation_model('PutObject').input_shape.members:put_args['IfNoneMatch']='*'
        stub.add_response('put_object',{},put_args)
        stub.add_response('head_object',{'ContentLength':len(data),'Metadata':{'sha256':digest}},args)
        write_asset('sdk.pdf',data)
        stub.assert_no_pending_responses()


def test_signature_failure_has_actionable_secret_safe_message():
    from botocore.exceptions import ClientError
    from backend.storage import failure
    exc=ClientError({'Error':{'Code':'SignatureDoesNotMatch','Message':'PRIVATE-SECRET-DO-NOT-LOG'}},'ListObjectsV2')
    message=str(failure(exc,'authentication'))
    assert 'SAME Cloudflare R2 S3 credentials pair' in message
    assert 'PRIVATE-SECRET' not in message


def test_token_conversion_only_retained_after_verified_auth(app,monkeypatch):
    import hashlib
    from backend import storage
    raw='example-api-token';derived=hashlib.sha256(raw.encode()).hexdigest()
    app.config['R2_SECRET_ACCESS_KEY']=raw
    def authenticate():
        if app.config['R2_SECRET_ACCESS_KEY']!=derived:
            raise storage.StorageError('SignatureDoesNotMatch')
    monkeypatch.setattr(storage,'check_access',authenticate)
    with app.app_context():assert storage.authenticate_or_convert_token() is True
    assert app.config['R2_SECRET_ACCESS_KEY']==derived
    app.config['R2_SECRET_ACCESS_KEY']=raw
    def fail():raise storage.StorageError('SignatureDoesNotMatch')
    monkeypatch.setattr(storage,'check_access',fail)
    with app.app_context():
        import pytest
        with pytest.raises(storage.StorageError):storage.authenticate_or_convert_token()
    assert app.config['R2_SECRET_ACCESS_KEY']==raw


def test_network_error_sanitization_handles_null_response():
    from backend.storage import failure
    error=RuntimeError('private details');error.response=None
    assert 'private details' not in str(failure(error,'authentication'))
