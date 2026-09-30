"""Optional Redis/Celery runner for the existing durable per-paper queue.

Run ONE beat scheduler. PostgreSQL ingestion state is authoritative; broker loss
does not lose uploaded jobs. This adapter never starts a catalog-wide import.
"""
import os
from celery import Celery
from redis import Redis
from . import create_app

flask_app=create_app()
broker=os.getenv('CELERY_BROKER_URL','')
if not broker:raise RuntimeError('CELERY_BROKER_URL is required for the Celery worker')
celery=Celery('pyq',broker=broker)
celery.conf.update(task_serializer='json',accept_content=['json'],task_ignore_result=True,
    worker_prefetch_multiplier=1,task_acks_late=True,task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,broker_transport_options={'visibility_timeout':1800},
    task_soft_time_limit=1500,task_time_limit=1650,
    beat_schedule={'pending-papers':{'task':'pyq.drain_one','schedule':5.0,'options':{'expires':5}}})


def drain_one(app, broker_client):
    # One bounded drain at a time: uploads and bounded catalog batches share it.
    # The lease exceeds the hard task limit and the DB stale-processing lease.
    lock=broker_client.lock(os.getenv('CELERY_QUEUE_NAMESPACE','pyq:ingestion')+':drain',timeout=1750,blocking=False)
    if not lock.acquire(blocking=False):return False
    try:
        with app.app_context():
            from .models import db
            from .acquisition import download_pending
            from .ingestion import work_once
            try:
                download_pending(app,workers=1,limit=1)
                return work_once()
            finally:db.session.remove()
    finally:
        try:lock.release()
        except Exception:pass


@celery.task(name='pyq.drain_one')
def drain_task():
    try:
        return drain_one(flask_app,Redis.from_url(broker,socket_connect_timeout=5,socket_timeout=5))
    except Exception as exc:
        # Do not let Celery log exception arguments containing URLs/credentials.
        flask_app.logger.error('ingestion_tick_failed type=%s',type(exc).__name__)
        return False
