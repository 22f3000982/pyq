"""Shared content cache. Student/session state is never cached here."""
import json, time, uuid, threading
from collections import OrderedDict
from flask import current_app, has_app_context
from sqlalchemy import event
from sqlalchemy.orm import Session
from .performance import count

CONTENT_TABLES = {'course', 'term', 'exam_type', 'paper', 'question', 'question_option',
                  'question_image', 'ingestion_file', 'source_entry'}

# A small per-process fallback matters on Render even before Redis is provisioned:
# the same paper should not be rebuilt from PostgreSQL for every student. Redis
# remains the preferred shared cache across processes/services.
_local_lock = threading.RLock()
_local_cache = OrderedDict()
_local_inflight = {}


def _local_limit():
    return max(8, int(current_app.config.get('LOCAL_CONTENT_CACHE_MAX', 128)))


def _local_ttl():
    return max(1, int(current_app.config.get('CONTENT_CACHE_TTL', 60)))


def _local_get(key):
    now=time.monotonic()
    with _local_lock:
        row=_local_cache.get(key)
        if row is None:return None
        expires,value=row
        if expires<=now:
            _local_cache.pop(key,None);return None
        _local_cache.move_to_end(key)
        return value


def _local_put(key,value):
    with _local_lock:
        _local_cache[key]=(time.monotonic()+_local_ttl(),value)
        _local_cache.move_to_end(key)
        while len(_local_cache)>_local_limit():_local_cache.popitem(last=False)


def _local_clear():
    with _local_lock:_local_cache.clear()


def _local_cached(key,loader):
    value=_local_get(key)
    if value is not None:
        count('cache_hit');return value
    count('cache_miss')
    owner=False
    with _local_lock:
        event=_local_inflight.get(key)
        if event is None:
            event=threading.Event();_local_inflight[key]=event;owner=True
    if not owner:
        # Let one thread warm a paper; a bounded wait avoids a thundering herd
        # during simultaneous exam starts without ever hanging a request.
        if event.wait(timeout=5.0):
            value=_local_get(key)
            if value is not None:
                count('cache_hit');return value
        return loader()
    try:
        value=loader();_local_put(key,value);return value
    finally:
        with _local_lock:
            _local_inflight.pop(key,None);event.set()


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
    _local_clear()
    try:
        r = client()
        if r is not None:r.set(prefix()+':epoch', uuid.uuid4().hex)
    except Exception:
        # Local entries are already cleared in this process. Other processes have
        # a bounded TTL even if shared invalidation is temporarily unavailable.
        current_app.logger.warning('content_cache_invalidation_failed; entries expire within configured TTL')


def cached(key, loader):
    lock = None
    acquired = False
    try:
        r = client()
    except Exception:
        count('cache_error');return _local_cached(key,loader)
    if r is None:return _local_cached(key,loader)
    try:
        epoch_key = prefix()+':epoch'
        r.set(epoch_key, uuid.uuid4().hex, nx=True)
        epoch = r.get(epoch_key)
        full = prefix()+':'+str(epoch)+':'+key
        raw = r.get(full)
        if raw is not None:
            count('cache_hit');return json.loads(raw)
        count('cache_miss')
        lock = r.lock(full+':lock', timeout=15, blocking_timeout=5.0)
        acquired = lock.acquire()
        raw = r.get(full)
        if raw is not None:
            if acquired:lock.release();acquired=False
            return json.loads(raw)
    except Exception:
        if acquired:
            try:lock.release()
            except Exception:pass
        count('cache_error');return _local_cached(key,loader)
    try:
        value = loader()  # Application exceptions propagate; no duplicate execution.
        if acquired:
            try:
                if r.get(epoch_key) == epoch:
                    r.set(full, json.dumps(value), ex=current_app.config.get('CONTENT_CACHE_TTL', 60))
            except Exception:count('cache_error')
        _local_put(key,value)
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
