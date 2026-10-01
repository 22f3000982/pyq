"""Google Drive OAuth and authenticated file download helpers."""
import base64,hashlib,secrets,time
from urllib.parse import urlencode
import requests
from cryptography.fernet import Fernet,InvalidToken
from flask import current_app,request,session
from .models import db,ExternalCredential

PROVIDER='google_drive'
AUTH_URL='https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL='https://oauth2.googleapis.com/token'
USERINFO_URL='https://openidconnect.googleapis.com/v1/userinfo'
DRIVE_SCOPE='https://www.googleapis.com/auth/drive.readonly'
IDENTITY_SCOPES='openid email'
ALL_SCOPES=IDENTITY_SCOPES+' '+DRIVE_SCOPE

def configured():
    return bool(current_app.config.get('GOOGLE_OAUTH_CLIENT_ID') and current_app.config.get('GOOGLE_OAUTH_CLIENT_SECRET'))

def redirect_uri():
    explicit=(current_app.config.get('GOOGLE_OAUTH_REDIRECT_URI') or '').strip()
    if explicit:return explicit
    return request.host_url.rstrip('/')+'/api/admin/google-drive/callback'

def _fernet():
    material=(current_app.config['SECRET_KEY']+'|google-drive-oauth-v1').encode()
    key=base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)

def _encrypt(token):
    return _fernet().encrypt(token.encode()).decode()

def _decrypt(value):
    try:return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:raise RuntimeError('Stored Google Drive credential can no longer be decrypted. Reconnect Google Drive.')

def credential():
    return ExternalCredential.query.filter_by(provider=PROVIDER).first()

def status():
    row=credential()
    return {
        'configured':configured(),
        'connected':bool(row),
        'email':row.account_email if row else None,
        'scope':row.scope if row else None,
        'redirect_uri':redirect_uri(),
    }

def authorization_url():
    if not configured():raise RuntimeError('Google OAuth Client ID/Secret are not configured on the server.')
    state=secrets.token_urlsafe(32);session['google_oauth_state']=state
    params={
        'client_id':current_app.config['GOOGLE_OAUTH_CLIENT_ID'],
        'redirect_uri':redirect_uri(),
        'response_type':'code',
        'scope':ALL_SCOPES,
        'access_type':'offline',
        'prompt':'consent',
        'include_granted_scopes':'true',
        'state':state,
    }
    return AUTH_URL+'?'+urlencode(params)

def complete_callback(code,state):
    expected=session.pop('google_oauth_state',None)
    if not expected or not secrets.compare_digest(expected,state or ''):
        raise RuntimeError('Google connection expired or state check failed. Start Connect Google Drive again.')
    if not code:raise RuntimeError('Google did not return an authorization code.')
    response=requests.post(TOKEN_URL,data={
        'client_id':current_app.config['GOOGLE_OAUTH_CLIENT_ID'],
        'client_secret':current_app.config['GOOGLE_OAUTH_CLIENT_SECRET'],
        'code':code,'grant_type':'authorization_code','redirect_uri':redirect_uri(),
    },timeout=(10,30))
    try:data=response.json()
    except Exception:data={}
    if response.status_code!=200:raise RuntimeError('Google token exchange failed. Check OAuth client settings and redirect URI.')
    refresh=data.get('refresh_token')
    row=credential()
    if not refresh and row:refresh=_decrypt(row.refresh_token_enc)
    if not refresh:raise RuntimeError('Google did not provide an offline refresh token. Revoke prior access and connect again.')
    access=data.get('access_token')
    email=None
    if access:
        user=requests.get(USERINFO_URL,headers={'Authorization':'Bearer '+access},timeout=(10,20))
        if user.status_code==200:
            try:email=user.json().get('email')
            except Exception:pass
    if not row:
        row=ExternalCredential(provider=PROVIDER,refresh_token_enc=_encrypt(refresh));db.session.add(row)
    else:row.refresh_token_enc=_encrypt(refresh)
    row.account_email=email;row.scope=data.get('scope') or ALL_SCOPES;row.updated_at=time.time()
    db.session.commit()
    return status()

def disconnect():
    row=credential()
    if row:
        db.session.delete(row);db.session.commit()
    return {'connected':False}

def access_token():
    row=credential()
    if not row:raise RuntimeError('Google Drive is not connected in Admin.')
    response=requests.post(TOKEN_URL,data={
        'client_id':current_app.config['GOOGLE_OAUTH_CLIENT_ID'],
        'client_secret':current_app.config['GOOGLE_OAUTH_CLIENT_SECRET'],
        'refresh_token':_decrypt(row.refresh_token_enc),
        'grant_type':'refresh_token',
    },timeout=(10,30))
    try:data=response.json()
    except Exception:data={}
    if response.status_code!=200 or not data.get('access_token'):
        raise RuntimeError('Google Drive authorization expired or was revoked. Reconnect Google Drive in Admin.')
    return data['access_token']

def download_file(file_id,destination,max_bytes=20*1024*1024):
    """Download an authenticated Drive file through the official Drive API."""
    token=access_token()
    url='https://www.googleapis.com/drive/v3/files/'+file_id
    response=requests.get(url,params={'alt':'media','supportsAllDrives':'true'},headers={'Authorization':'Bearer '+token},stream=True,timeout=(10,60))
    if response.status_code in (401,403):
        response.close();raise RuntimeError('Google Drive denied this file. Confirm the connected account can open the source paper.')
    if response.status_code==404:
        response.close();raise RuntimeError('Google Drive file was not found or is not shared with the connected account.')
    if response.status_code!=200:
        code=response.status_code;response.close();raise RuntimeError(f'Google Drive API returned HTTP {code}.')
    length=int(response.headers.get('Content-Length','0') or 0)
    if length>max_bytes:response.close();raise RuntimeError('Source exceeds download byte limit')
    size=0;sha=hashlib.sha256();first=True
    try:
        with open(destination,'wb') as out:
            for block in response.iter_content(65536):
                if not block:continue
                if first:
                    first=False
                    if not block.startswith(b'%PDF-'):
                        raise RuntimeError('Google Drive source is not a PDF file.')
                size+=len(block)
                if size>max_bytes:raise RuntimeError('Source exceeds download byte limit')
                sha.update(block);out.write(block)
    except Exception:
        from pathlib import Path
        Path(destination).unlink(missing_ok=True);raise
    finally:response.close()
    if not size:raise RuntimeError('Google Drive returned an empty file.')
    return {'hash':sha.hexdigest(),'size':size,'resolved_url':url}
