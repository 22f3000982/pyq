"""Best-effort anonymous analytics, isolated from learner transactions.

One bounded queue and one lazy writer per web process (safe with Gunicorn preload).
Only plain snapshots cross the thread boundary. Permanent reporting reads daily
aggregates; 30-day receipts deduplicate retries, then are removed in bounded batches.
"""
import os
import queue
import threading
import time
from datetime import datetime, timedelta, timezone
from flask import current_app, has_request_context, request
from sqlalchemy import create_engine, select, delete, func, text
from sqlalchemy.pool import QueuePool
from .models import db, AnalyticsDaily, AnalyticsReceipt

IST = timezone(timedelta(hours=5, minutes=30))
RETENTION = 30 * 86400

def paper_context(paper):
    ua = request.headers.get('User-Agent', '').lower() if has_request_context() else ''
    device = 'mobile' if any(v in ua for v in ('mobile', 'android', 'iphone', 'ipad')) else ('desktop' if ua else 'unknown')
    return dict(paper_key=paper.identity, paper_name=paper.name,
                course_key=paper.course.code or str(paper.course_id),
                course_name=paper.course.name, device=device)

def snapshot(attempt, automatic=False):
    context = attempt.analytics_context
    if not context or not attempt.records_progress:
        return None  # Do not invent history for pre-installation or collection attempts.
    return {**context, 'key': f'{attempt.id}:{attempt.started_at:.6f}',
            'mode': context.get('initial_mode',attempt.mode), 'started_at': attempt.started_at,
            'submitted_at': attempt.submitted_at, 'automatic': automatic}

def enqueue(event):
    if not event:
        return
    try:
        collector = current_app.extensions.get('analytics')
        if collector:
            collector.put(event)
    except Exception:
        # Analytics must never change the outcome of a committed learner action.
        current_app.logger.warning('Analytics event could not be queued')

def persist(engine, events, now=None):
    """Idempotent receipt + aggregate increments in one isolated transaction."""
    now = time.time() if now is None else now
    dialect = engine.dialect.name
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise ValueError('Unsupported analytics database')
    receipt, daily = AnalyticsReceipt.__table__, AnalyticsDaily.__table__
    with engine.begin() as conn:
        if dialect == 'postgresql':
            conn.execute(text("SET LOCAL statement_timeout = '2000ms'"))
            conn.execute(text("SET LOCAL lock_timeout = '250ms'"))
        for e in events:
            if e['started_at'] < now - RETENTION:
                continue  # Old replays cannot recreate deleted receipts.
            added = conn.execute(insert(receipt).values(key=e['key'], started_at=e['started_at'], completed=False)
                                 .on_conflict_do_nothing(index_elements=['key']).returning(receipt.c.key)).first()
            completed = False
            if e['submitted_at'] is not None:
                completed = conn.execute(receipt.update().where(receipt.c.key == e['key'], receipt.c.completed.is_(False))
                                         .values(completed=True).returning(receipt.c.key)).first() is not None
            if not added and not completed:
                continue
            day = datetime.fromtimestamp(e['started_at'], IST).date().isoformat()
            # A mode switch keeps the original aggregate group: captured at start.
            values = {k:e[k] for k in ('paper_key','paper_name','course_key','course_name','device','mode')}
            values.update(day=day, starts=int(bool(added)), completions=int(completed),
                          automatic=int(completed and e['automatic']),
                          elapsed_seconds=max(0, e['submitted_at']-e['started_at']) if completed else 0)
            stmt = insert(daily).values(**values)
            conn.execute(stmt.on_conflict_do_update(index_elements=['day','paper_key','mode','device'],
                set_={k:daily.c[k]+stmt.excluded[k] for k in ('starts','completions','automatic','elapsed_seconds')}))
        old = select(receipt.c.key).where(receipt.c.started_at < now-RETENTION).limit(100)
        conn.execute(delete(receipt).where(receipt.c.key.in_(old)))

class Collector:
    def __init__(self, app):
        self.app = app
        self.pid = os.getpid()
        self.queue = queue.Queue(maxsize=max(1,int(app.config.get('ANALYTICS_QUEUE_SIZE', 1000))))
        self.thread = None
        self.lock = threading.Lock()
        self.dropped = 0
        self.failed = 0
        self.engine = None
        self.stop = threading.Event()

    def put(self, event):
        if self.pid != os.getpid():
            # No thread/connection created before fork; replace inherited queue.
            replacement = Collector(self.app)
            self.app.extensions['analytics'] = replacement
            return replacement.put(event)
        try:
            self.queue.put_nowait(dict(event))
        except queue.Full:
            self.dropped += 1
            return
        if not self.app.config.get('ANALYTICS_MANUAL_FLUSH', self.app.testing):
            with self.lock:
                if not self.thread:
                    self.thread = threading.Thread(target=self.run, daemon=True, name='analytics-writer')
                    self.thread.start()

    def connection_engine(self):
        if self.engine is None:
            with self.app.app_context():
                url = db.engine.url
                options = dict(self.app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}))
                options.update(poolclass=QueuePool, pool_size=1, max_overflow=0, pool_timeout=1)
                args = dict(options.get('connect_args', {}))
                if url.get_backend_name() == 'postgresql':
                    args['connect_timeout'] = 2
                else:
                    args.update(timeout=0.1, check_same_thread=False)
                options['connect_args'] = args
                self.engine = create_engine(url, **options)
        return self.engine

    def flush(self):
        batch = []
        for _ in range(100):
            try:
                batch.append(self.queue.get_nowait())
            except queue.Empty:
                break
        if not batch:
            return
        try:
            persist(self.connection_engine(), batch)
        except Exception:
            self.failed += len(batch)
            self.app.logger.warning('Analytics batch dropped (%s events); learner actions unaffected', len(batch))
        finally:
            for _ in batch:
                self.queue.task_done()

    def run(self):
        while not self.stop.wait(1):
            self.flush()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)
        if self.engine:
            self.engine.dispose()

def install(app):
    if app.config.get('ANALYTICS_ENABLED', True):
        app.extensions['analytics'] = Collector(app)

def report(period, now=None):
    today = datetime.fromtimestamp(time.time() if now is None else now, IST).date()
    first = today if period == 'today' else today-timedelta(days=6) if period == '7d' else None
    columns = [func.sum(getattr(AnalyticsDaily,k)).label(k) for k in ('starts','completions','automatic','elapsed_seconds')]
    query = db.session.query(*columns)
    if first:
        query = query.filter(AnalyticsDaily.day >= first.isoformat())
    query = query.filter(AnalyticsDaily.day <= today.isoformat())
    def metrics(row):
        data = {k:row._mapping[k] or 0 for k in ('starts','completions','automatic','elapsed_seconds')}
        data.update(completion_rate=round(100*data['completions']/data['starts'],1) if data['starts'] else None,
                    average_seconds=round(data['elapsed_seconds']/data['completions']) if data['completions'] else None)
        return data
    total = metrics(query.one())
    papers = query.add_columns(AnalyticsDaily.paper_key, func.max(AnalyticsDaily.paper_name).label('name')).group_by(AnalyticsDaily.paper_key).order_by(func.sum(AnalyticsDaily.starts).desc(),AnalyticsDaily.paper_key).limit(50).all()
    courses = query.add_columns(AnalyticsDaily.course_key, func.max(AnalyticsDaily.course_name).label('name')).group_by(AnalyticsDaily.course_key).order_by(func.sum(AnalyticsDaily.starts).desc(),AnalyticsDaily.course_key).limit(50).all()
    devices = query.add_columns(AnalyticsDaily.device).group_by(AnalyticsDaily.device).all()
    collector = current_app.extensions.get('analytics')
    return dict(period=period, timezone='Asia/Kolkata', totals=total,
                papers=[dict(key=r.paper_key,name=r.name,**metrics(r)) for r in papers],
                courses=[dict(key=r.course_key,name=r.name,**metrics(r)) for r in courses],
                devices=[dict(device=r.device,**metrics(r)) for r in devices],
                first_day=db.session.query(func.min(AnalyticsDaily.day)).scalar(),
                writer=dict(queued=collector.queue.qsize(), dropped=collector.dropped, failed=collector.failed) if collector else None)
