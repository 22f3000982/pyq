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
