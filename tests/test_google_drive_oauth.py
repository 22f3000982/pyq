import io
from urllib.parse import urlparse,parse_qs
from backend.models import db,ExternalCredential
from backend.acquisition import fetch_pdf
from conftest import login

class Response:
    def __init__(self,status=200,data=None,content=b''):
        self.status_code=status;self._data=data or {};self.content=content;self.headers={}
    def json(self):return self._data
    def close(self):pass
    def iter_content(self,n):
        if self.content:yield self.content

def test_google_drive_status_and_oauth_callback(app,client,monkeypatch):
    h=login(client,True)
    app.config.update(GOOGLE_OAUTH_CLIENT_ID='client-id',GOOGLE_OAUTH_CLIENT_SECRET='client-secret')
    status=client.get('/api/admin/google-drive/status',headers=h)
    assert status.status_code==200
    assert status.json['configured'] is True and status.json['connected'] is False
    assert status.json['redirect_uri'].endswith('/api/admin/google-drive/callback')

    connect=client.get('/api/admin/google-drive/connect',headers=h)
    assert connect.status_code==302
    query=parse_qs(urlparse(connect.headers['Location']).query)
    assert query['client_id']==['client-id']
    assert 'https://www.googleapis.com/auth/drive.readonly' in query['scope'][0]
    state=query['state'][0]

    import backend.google_drive as gd
    monkeypatch.setattr(gd.requests,'post',lambda *a,**k:Response(200,{
        'access_token':'access','refresh_token':'refresh-secret','scope':gd.ALL_SCOPES
    }))
    monkeypatch.setattr(gd.requests,'get',lambda *a,**k:Response(200,{'email':'student@example.edu'}))
    done=client.get('/api/admin/google-drive/callback?code=abc&state='+state,headers=h)
    assert done.status_code==302
    row=ExternalCredential.query.filter_by(provider='google_drive').one()
    assert row.account_email=='student@example.edu'
    assert 'refresh-secret' not in row.refresh_token_enc
    status=client.get('/api/admin/google-drive/status',headers=h)
    assert status.json['connected'] is True

def test_authenticated_drive_download_is_used_when_connected(app,tmp_path,monkeypatch):
    app.config.update(GOOGLE_OAUTH_CLIENT_ID='client-id',GOOGLE_OAUTH_CLIENT_SECRET='client-secret')
    import backend.google_drive as gd
    with app.app_context():
        row=ExternalCredential(provider='google_drive',account_email='x@example.edu',refresh_token_enc=gd._encrypt('refresh'))
        db.session.add(row);db.session.commit()
        called={}
        def fake_download(file_id,destination,max_bytes):
            called['id']=file_id
            data=b'%PDF-1.4\n% fake pdf'
            destination.write_bytes(data)
            import hashlib
            return {'hash':hashlib.sha256(data).hexdigest(),'size':len(data),'resolved_url':'drive-api'}
        monkeypatch.setattr(gd,'download_file',fake_download)
        out=tmp_path/'paper.pdf'
        result=fetch_pdf('https://drive.google.com/file/d/FILE123/view?usp=sharing',out)
        assert called['id']=='FILE123'
        assert out.read_bytes().startswith(b'%PDF-')
        assert result['resolved_url']=='drive-api'

def test_disconnect_removes_stored_refresh_token(app,client):
    h=login(client,True)
    app.config.update(GOOGLE_OAUTH_CLIENT_ID='client-id',GOOGLE_OAUTH_CLIENT_SECRET='client-secret')
    import backend.google_drive as gd
    row=ExternalCredential(provider='google_drive',refresh_token_enc=gd._encrypt('refresh'))
    db.session.add(row);db.session.commit()
    r=client.post('/api/admin/google-drive/disconnect',headers=h,json={})
    assert r.status_code==200
    assert ExternalCredential.query.count()==0
