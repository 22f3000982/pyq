import os, secrets, gzip, re
from pathlib import Path
from flask import Flask, jsonify, request, session, send_from_directory, abort
from sqlalchemy import text
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import IntegrityError,SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from .models import db

limiter = Limiter(key_func=get_remote_address, default_limits=['300 per minute'])

def create_app(config=None):
    from .database_config import database_url,engine_options
    from dotenv import load_dotenv
    load_dotenv()
    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, static_folder=None, instance_path=str(root / 'instance'))
    Path(app.instance_path).mkdir(exist_ok=True)
    supplied=config or {}
    secret = os.getenv('SECRET_KEY')
    if not secret and not (config or {}).get('TESTING'):
        raise RuntimeError('Set SECRET_KEY to a random value (see README).')
    configured_uri=supplied.get('SQLALCHEMY_DATABASE_URI')
    production_env=os.getenv('RENDER','').lower()=='true' or os.getenv('FLASK_ENV','').lower()=='production' or os.getenv('APP_ENV','').lower()=='production'
    if not (os.getenv('DATABASE_URL','').strip() or configured_uri) and production_env:
        raise RuntimeError('DATABASE_URL is required on Render; refusing an implicit SQLite production fallback.')
    default_upload_dir='/data/uploads' if production_env else str(root/'uploads')
    app.config.update(SECRET_KEY=secret or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=database_url(os.getenv('DATABASE_URL'),'sqlite:///' + str(root/'instance/app.db')),
        SQLALCHEMY_TRACK_MODIFICATIONS=False, MAX_CONTENT_LENGTH=110*1024*1024,
        UPLOAD_DIR=os.getenv('UPLOAD_DIR', default_upload_dir),
        MAX_UPLOAD_SIZE=int(os.getenv('MAX_UPLOAD_SIZE', 110*1024*1024)),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','false').lower()=='true',
        PERMANENT_SESSION_LIFETIME=86400,
        RATELIMIT_STORAGE_URI=os.getenv('RATELIMIT_STORAGE_URI','memory://'),
        LLM_PROVIDER=os.getenv('LLM_PROVIDER','none'), LLM_API_KEY=os.getenv('LLM_API_KEY',''),
        LLM_MODEL=os.getenv('LLM_MODEL',''), LLM_BASE_URL=os.getenv('LLM_BASE_URL',''),
        OCR_ENABLED=os.getenv('OCR_ENABLED','true').lower()=='true',
        CATALOG_AUTO_PROCESS=os.getenv('CATALOG_AUTO_PROCESS','false').lower()=='true',
        GOOGLE_OAUTH_CLIENT_ID=os.getenv('GOOGLE_OAUTH_CLIENT_ID',''),
        GOOGLE_OAUTH_CLIENT_SECRET=os.getenv('GOOGLE_OAUTH_CLIENT_SECRET',''),
        GOOGLE_OAUTH_REDIRECT_URI=os.getenv('GOOGLE_OAUTH_REDIRECT_URI',''))
    legacy_bucket=os.getenv('R2_BUCKET_NAME','')
    storage_backend=os.getenv('STORAGE_BACKEND','local').lower()
    image_delivery=os.getenv('IMAGE_DELIVERY','').strip().lower()
    # Existing Render services can keep an old/missing proxy variable even after
    # render.yaml changes. In production R2, prefer private direct signed delivery
    # so tiny question images never traverse Flask unless their direct URL fails.
    if production_env and storage_backend=='r2' and image_delivery in ('','proxy'):
        image_delivery='signed'
    elif not image_delivery:
        image_delivery='proxy'
    app.config.update(STORAGE_BACKEND=storage_backend,R2_ENDPOINT_URL=os.getenv('R2_ENDPOINT_URL',''),R2_ACCESS_KEY_ID=os.getenv('R2_ACCESS_KEY_ID',''),R2_SECRET_ACCESS_KEY=os.getenv('R2_SECRET_ACCESS_KEY',''),R2_BUCKET_NAME=legacy_bucket,R2_PDF_BUCKET_NAME=os.getenv('R2_PDF_BUCKET_NAME',''),R2_IMAGE_BUCKET_NAME=os.getenv('R2_IMAGE_BUCKET_NAME',''),R2_PREFIX=os.getenv('R2_PREFIX','pyq'))
    app.config.update(CONTENT_CACHE_URL=os.getenv('REDIS_URL',''), CACHE_NAMESPACE=os.getenv('CACHE_NAMESPACE','pyq:content:v1'), CONTENT_CACHE_TTL=int(os.getenv('CONTENT_CACHE_TTL','60')), IMAGE_DELIVERY=image_delivery, IMAGE_CDN_BASE_URL=os.getenv('IMAGE_CDN_BASE_URL',''), IMAGE_CDN_MANIFEST=os.getenv('IMAGE_CDN_MANIFEST',''))
    if config: app.config.update(config)
    from . import content_cache
    from .storage import configure_delivery
    configure_delivery(app)
    if app.config['STORAGE_BACKEND'] not in ('local','r2'):raise ValueError('STORAGE_BACKEND must be local or r2')
    if production_env:
        from sqlalchemy.engine import make_url
        if make_url(app.config['SQLALCHEMY_DATABASE_URI']).get_backend_name()!='postgresql':
            raise RuntimeError('Production requires PostgreSQL; SQLite fallback is disabled.')
        if app.config['STORAGE_BACKEND']!='r2':
            raise RuntimeError('Production requires private R2 storage; local fallback is disabled.')
    if production_env and app.config['STORAGE_BACKEND']=='r2':
        required_r2=('R2_ENDPOINT_URL','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY','R2_PDF_BUCKET_NAME','R2_IMAGE_BUCKET_NAME')
        if any(not app.config.get(key) for key in required_r2):
            raise RuntimeError('R2 production configuration requires the endpoint, credential pair, and separate PDF/image bucket names.')
    app.config.setdefault('SQLALCHEMY_ENGINE_OPTIONS',engine_options(app.config['SQLALCHEMY_DATABASE_URI']))
    upload_path=Path(app.config['UPLOAD_DIR'])
    app.config['UPLOAD_DIR']=str((root/upload_path).resolve() if not upload_path.is_absolute() else upload_path)
    Path(app.config['UPLOAD_DIR']).mkdir(parents=True, exist_ok=True)
    db.init_app(app); Migrate(app, db); limiter.init_app(app)
    from .performance import install
    install(app, db)
    @app.before_request
    def csrf():
        if request.path.startswith('/api/') and request.method in ('POST','PUT','PATCH','DELETE'):
            expected=session.get('csrf','')
            if not expected or not secrets.compare_digest(expected,request.headers.get('X-CSRF-Token','')):
                return jsonify(error='Refresh the page and try again.', code='CSRF'),403
    @app.after_request
    def security(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['X-Frame-Options']='SAMEORIGIN'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-src 'self' https://tcsion.com https://www.tcsion.com; object-src 'none'; base-uri 'self'"
        if app.extensions.get('image_origin'):
            response.headers['Content-Security-Policy']=response.headers['Content-Security-Policy'].replace("img-src 'self' data:","img-src 'self' data: "+app.extensions['image_origin'])
        if request.path.startswith('/api/') and not request.path.startswith('/api/images/'): response.headers['Cache-Control']='no-store'
        # Compress shared public content only; session/CSRF and answer APIs are excluded.
        shared=request.path in ('/api/home','/api/stats','/api/catalog','/api/metadata','/api/courses','/api/papers','/api/demo-papers') or bool(re.fullmatch(r'/api/papers/\d+/questions',request.path))
        if shared:
            response.vary.add('Accept-Encoding')
            if request.method=='GET' and response.status_code==200 and request.accept_encodings['gzip']>0 and not response.headers.get('Content-Encoding') and not response.direct_passthrough:
                data=response.get_data()
                if len(data)>1024:
                    compressed=gzip.compress(data,compresslevel=5,mtime=0)
                    if len(compressed)<len(data):response.set_data(compressed);response.headers['Content-Encoding']='gzip'
        return response
    @app.get('/healthz')
    def healthz():
        try:
            with db.engine.connect() as connection:
                connection.execute(text('SELECT 1'))
            return jsonify(status='ok'),200
        except Exception:
            return jsonify(status='unavailable'),503
    from .storage import StorageError
    @app.errorhandler(StorageError)
    def storage_error(e):
        app.logger.warning('Asset delivery failed: %s',str(e))
        return jsonify(error='Source asset is temporarily unavailable. Please retry.'),503
    @app.errorhandler(SQLAlchemyError)
    def database_error(e):
        db.session.rollback()
        app.logger.error('Database request failed (%s)',type(e).__name__)
        return jsonify(error='Database is temporarily unavailable. Please retry.'),503
    @app.errorhandler(HTTPException)
    def http_error(e):
        if e.code==404 and not request.path.startswith('/api/'):
            from flask import render_template
            return render_template('not_found.html'),404
        return jsonify(error=e.description),e.code
    @app.errorhandler(IntegrityError)
    def conflict(e):
        db.session.rollback(); return jsonify(error='This record already exists or conflicts with related data.'),409
    @app.errorhandler(StaleDataError)
    def stale(e):
        db.session.rollback(); return jsonify(error='Attempt changed in another request. Reload and retry.'),409
    @app.errorhandler(ValueError)
    def invalid(e):
        db.session.rollback(); return jsonify(error=str(e)),400
    from .ai_solutions import bp as ai_solutions
    app.register_blueprint(ai_solutions)
    from .study_pages import study
    app.register_blueprint(study)
    from .site_pages import site,metadata
    app.register_blueprint(site)
    from .about_api import about
    app.register_blueprint(about)
    from .api import api
    app.register_blueprint(api)
    try:
        from .exam_api import exams
        app.register_blueprint(exams)
    except ModuleNotFoundError as e:
        if e.name!='backend.exam_api': raise
    try:
        from .admin_api import admin
        app.register_blueprint(admin)
    except ModuleNotFoundError as e:
        if e.name!='backend.admin_api': raise
    @app.route('/', defaults={'path':''})
    @app.route('/<path:path>')
    def frontend(path):
        if path.startswith('api/'): return jsonify(error='Not found'),404
        dist=root/'frontend/dist'
        if path and (dist/path).is_file() and (dist/path).resolve().is_relative_to(dist):
            response=send_from_directory(dist,path)
            if re.fullmatch(r'assets/[^/]+-[A-Za-z0-9_-]{8,}\.(js|css|woff2?)',path):response.headers['Cache-Control']='public, max-age=31536000, immutable'
            return response
        if path and not re.fullmatch(r'(?:about|bookmarks|progress|history|dashboard|mistakes|login|admin(?:/login)?|(?:course|paper|attempt|result)/[0-9]+|exam/[^/]+)',path):
            abort(404)
        if not (dist/'index.html').exists(): return jsonify(message='Build frontend with npm run build'),503
        html=(dist/'index.html').read_text()
        from markupsafe import escape
        meta=metadata();tags='<link rel="canonical" href="'+str(escape(meta['canonical_url']))+'">'
        for name,key in [('google-site-verification','site_verification'),('google-adsense-account','adsense_account')]:
            if meta[key]:tags+='<meta name="'+name+'" content="'+str(escape(meta[key]))+'">'
        response=app.response_class(html.replace('</head>',tags+'</head>',1),mimetype='text/html');response.headers['Cache-Control']='no-cache'
        if path.startswith(('admin','attempt/','result/','login','progress','bookmarks','history','dashboard','mistakes')):response.headers['X-Robots-Tag']='noindex, nofollow'
        return response
    from .cli import register_cli
    register_cli(app)
    return app
