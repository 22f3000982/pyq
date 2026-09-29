"""Shared, server-only content cache. Never cache sessions, responses or progress."""
import json, time, uuid
from flask import current_app, has_app_context
from sqlalchemy import event
from sqlalchemy.orm import Session
from .performance import count

CONTENT_TABLES = {'course', 'term', 'exam_type', 'paper', 'question', 'question_option',
                  'question_image', 'ingestion_file', 'source_entry'}


def client():
    app = current_app
    if not app.config.get('CONTENT_CACHE_URL'):
        return None
    if 'content_redis' not in app.extensions:
        from redis import Redis
        app.extensions['content_redis'] = Redis.from_url(app.config['CONTENT_CACHE_URL'],
            socket_connect_timeout=.3, socket_timeout=.3, decode_responses=True,
            max_connections=16)
    return app.extensions['content_redis']


def prefix():
    return current_app.config.get('CACHE_NAMESPACE', 'pyq:content:v1')


def invalidate():
    try:
        r = client()
        if r is not None:
            r.set(prefix()+':epoch', uuid.uuid4().hex)
    except Exception:
        # Entries have a bounded TTL even if invalidation delivery is unavailable.
        current_app.logger.warning('content_cache_invalidation_failed; entries expire within configured TTL')


def cached(key, loader):
    lock = None
    acquired = False
    try:
        r = client()
    except Exception:
        count('cache_error');return loader()
    if r is None:return loader()
    try:
        epoch_key = prefix()+':epoch'
        r.set(epoch_key, uuid.uuid4().hex, nx=True)
        epoch = r.get(epoch_key)
        full = prefix()+':'+str(epoch)+':'+key
        raw = r.get(full)
        if raw is not None:
            count('cache_hit');return json.loads(raw)
        count('cache_miss')
        lock = r.lock(full+':lock', timeout=15, blocking_timeout=.5)
        acquired = lock.acquire()
        raw = r.get(full)
        if raw is not None:
            if acquired:lock.release();acquired=False
            return json.loads(raw)
    except Exception:
        if acquired:
            try:lock.release()
            except Exception:pass
        count('cache_error');return loader()
    try:
        value = loader()  # Application exceptions propagate; no duplicate execution.
        if acquired:
            try:
                if r.get(epoch_key) == epoch:
                    r.set(full, json.dumps(value), ex=current_app.config.get('CONTENT_CACHE_TTL', 60))
            except Exception:count('cache_error')
        return value
    finally:
        if acquired:
            try:lock.release()
            except Exception:pass


@event.listens_for(Session, 'before_flush')
def changed(session, context, instances):
    if any(getattr(obj, '__tablename__', '') in CONTENT_TABLES
           for obj in session.new.union(session.dirty).union(session.deleted)):
        session.info['content_changed'] = True


@event.listens_for(Session, 'do_orm_execute')
def bulk_changed(state):
    if state.is_update or state.is_delete or state.is_insert:
        table = getattr(state.statement, 'table', None)
        if getattr(table, 'name', None) in CONTENT_TABLES:
            state.session.info['content_changed'] = True


@event.listens_for(Session, 'after_commit')
def committed(session):
    if session.in_nested_transaction():
        return
    if session.info.pop('content_changed', False) and has_app_context():
        invalidate()


@event.listens_for(Session, 'after_soft_rollback')
def rolled_back(session, previous):
    if previous.parent is None:
        session.info.pop('content_changed', None)
