"""Conservative defaults; select final counts from staging load measurements."""
import os
bind = '0.0.0.0:'+os.getenv('PORT','5000')
worker_class = 'gthread'
workers = int(os.getenv('WEB_CONCURRENCY','2'))
threads = int(os.getenv('GUNICORN_THREADS','4'))
timeout = int(os.getenv('GUNICORN_TIMEOUT','60'))
graceful_timeout = 30
keepalive = 5
max_requests = 2000
max_requests_jitter = 200
accesslog = '-'
errorlog = '-'
# No query strings, signed URLs, headers or request bodies in access logs.
access_log_format = '%(m)s %(s)s %(D)s'


def post_worker_init(worker):
    # Shift first-use DB/signing/catalog setup out of the first learner request.
    # A temporary warmup failure must not prevent the service from starting.
    try:
        from backend.warmup import warm_public_content
        elapsed=warm_public_content(worker.wsgi)
        worker.log.info('public_content_warmup_ms=%d',elapsed)
    except Exception as exc:
        worker.log.warning('public_content_warmup_failed type=%s',type(exc).__name__)
