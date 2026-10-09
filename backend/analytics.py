"""Permanent minimal analytics; reads and aggregation only in the admin dashboard.

One insert/update is piggybacked on the existing transaction, in an isolated
savepoint. No daemon queue, additional browser requests, or answer tracking.
"""
import csv
import hashlib
import hmac
import io
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from flask import current_app, g, has_request_context, request
from sqlalchemy import func, case, select
from .models import db, AnalyticsEvent

IST = timezone(timedelta(hours=5, minutes=30))
_cache = {}
_lock = threading.Lock()
COOKIE = 'pyq-usage-browser'

def day(timestamp):
    return datetime.fromtimestamp(timestamp, IST).date().isoformat()

def event_key(attempt):
    return f'{attempt.id}:{attempt.started_at:.6f}'

def paper_context(paper):
    ua = request.headers.get('User-Agent', '').lower()
    device = 'mobile' if any(v in ua for v in ('mobile','android','iphone','ipad')) else 'desktop' if ua else 'unknown'
    token = request.cookies.get(COOKIE, '')
    if len(token) != 43 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in token):
        token = secrets.token_urlsafe(32)
        g.analytics_cookie = token
    browser = hmac.new(str(current_app.secret_key).encode(), ('usage:'+token).encode(), hashlib.sha256).hexdigest()
    return dict(paper_key=paper.identity,paper_name=paper.name,
                course_key=paper.course.code or str(paper.course_id),course_name=paper.course.name,
                device=device,browser_key=browser,initial_mode=paper and request.get_json().get('mode','practice'))

def install(app):
    @app.before_request
    def reset_usage_cookie():
        g.pop('analytics_cookie',None)

    @app.after_request
    def usage_cookie(response):
        if getattr(g,'analytics_cookie',None) and 200 <= response.status_code < 300:
            response.set_cookie(COOKIE,g.analytics_cookie,max_age=365*86400,httponly=True,
                                secure=app.config.get('SESSION_COOKIE_SECURE',False),samesite='Lax')
        return response

def record(attempt,automatic=False):
    if not current_app.config.get('ANALYTICS_ENABLED',True) or not attempt.analytics_context:
        return
    e=attempt.analytics_context
    # Main attempt changes have been flushed before this savepoint. A failure
    # here rolls back only analytics, so the existing action may still commit.
    try:
        dialect=db.engine.dialect.name
        if dialect=='postgresql':
            from sqlalchemy.dialects.postgresql import insert
        elif dialect=='sqlite':
            from sqlalchemy.dialects.sqlite import insert
        else:return
        table=AnalyticsEvent.__table__
        values={k:e[k] for k in ('paper_key','paper_name','course_key','course_name','device','browser_key','initial_mode')}
        values.update(key=event_key(attempt),started_at=attempt.started_at,start_day=day(attempt.started_at),
                      expires_at=attempt.expires_at,automatic=automatic,
                      completed_at=attempt.submitted_at,completion_mode=('assisted_exam' if e.get('assisted') and attempt.mode=='exam' else attempt.mode) if attempt.submitted_at is not None else None)
        stmt=insert(table).values(**values)
        if attempt.submitted_at is None:
            stmt=stmt.on_conflict_do_nothing(index_elements=['key'])
        else:
            stmt=stmt.on_conflict_do_update(index_elements=['key'],set_={k:stmt.excluded[k] for k in
                ('completed_at','completion_mode','automatic','expires_at')},where=table.c.completed_at.is_(None))
        with db.session.begin_nested():
            db.session.execute(stmt)
    except Exception:
        current_app.logger.warning('Analytics write failed; main learner transaction retained',exc_info=True)


def update_expiry(attempt):
    if not attempt.analytics_context:return
    try:
        with db.session.begin_nested():
            db.session.execute(AnalyticsEvent.__table__.update().where(AnalyticsEvent.key==event_key(attempt)).values(expires_at=attempt.expires_at))
    except Exception:
        current_app.logger.warning('Analytics expiry update failed')


def date_range(period,start=None,end=None,now=None):
    today=datetime.fromtimestamp(time.time() if now is None else now,IST).date()
    if period=='custom':
        try:
            first=datetime.strptime(start,'%Y-%m-%d').date()
            last=datetime.strptime(end,'%Y-%m-%d').date()
        except (ValueError,TypeError):raise ValueError('Use YYYY-MM-DD dates')
        if first>last or last>today:raise ValueError('Choose a past or current date range')
    elif period in ('today','7d','30d','all'):
        first=today-timedelta(days={'today':0,'7d':6,'30d':29}[period]) if period!='all' else None
        last=today
    else:raise ValueError('Choose today, 7d, 30d, all or custom')
    return first.isoformat() if first else None,last.isoformat()


def report(period,start=None,end=None,now=None):
    now=time.time() if now is None else now
    first,last=date_range(period,start,end,now)
    E=AnalyticsEvent
    cols=[func.count(E.key).label('starts'),func.count(E.completed_at).label('completions'),
          func.count(func.distinct(E.browser_key)).label('active_browsers'),
          func.sum(case((E.initial_mode=='exam',1),else_=0)).label('exam_starts'),
          func.sum(case((E.initial_mode=='practice',1),else_=0)).label('practice_starts'),
          func.sum(case(((E.initial_mode=='exam')&(E.completion_mode=='exam'),1),else_=0)).label('exam_completions'),
          func.sum(case(((E.initial_mode=='exam')&(E.completion_mode.in_(['practice','assisted_exam'])),1),else_=0)).label('switched_completions'),
          func.sum(case((E.automatic.is_(True),1),else_=0)).label('automatic'),
          func.sum(case((E.completed_at.is_(None)&(E.expires_at<=now),1),else_=0)).label('abandoned'),
          func.avg(E.completed_at-E.started_at).label('average_seconds')]
    q=db.session.query(*cols).filter(E.start_day<=last)
    if first:q=q.filter(E.start_day>=first)
    def metrics(row):
        m=dict(row._mapping)
        for k in ('exam_starts','practice_starts','exam_completions','switched_completions','automatic','abandoned'):m[k]=m[k] or 0
        m['average_seconds']=round(m['average_seconds'],1) if m['average_seconds'] is not None else None
        m['completion_rate']=round(100*m['completions']/m['starts'],1) if m['starts'] else None
        m['dropoff_rate']=round(100*m['abandoned']/m['starts'],1) if m['starts'] else None
        return m
    # Each chart/table is bounded; the totals still include all matching rows.
    def groups(column):
        return [metrics(r) for r in q.add_columns(column.label('name')).group_by(column).order_by(func.count(E.key).desc(),column).limit(50)]
    papers=[metrics(r) for r in q.add_columns(E.paper_key.label('key'),func.max(E.paper_name).label('name')).group_by(E.paper_key).order_by(func.count(E.key).desc(),E.paper_key).limit(50)]
    courses=[metrics(r) for r in q.add_columns(E.course_key.label('key'),func.max(E.course_name).label('name')).group_by(E.course_key).order_by(func.count(E.key).desc(),E.course_key).limit(50)]
    trend=[metrics(r) for r in q.add_columns(E.start_day.label('day')).group_by(E.start_day).order_by(E.start_day.desc()).limit(90)][::-1]
    return dict(period=period,first=first,last=last,timezone='Asia/Kolkata',totals=metrics(q.one()),
                papers=papers,courses=courses,devices=groups(E.device),trend=trend,
                first_day=db.session.query(func.min(E.start_day)).scalar(),generated_at=now)


def cached_report(period,start=None,end=None):
    # Admin reads only: no cache invalidation or computation on learner actions.
    key=(id(current_app._get_current_object()),period,start,end)
    now=time.time()
    with _lock:
        hit=_cache.get(key)
        if hit and now-hit[0]<30:return hit[1]
    result=report(period,start,end)
    with _lock:
        if len(_cache)>=64:_cache.clear()
        _cache[key]=(now,result)
    return result


def csv_report(result):
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['MauryaHub usage analytics','IST',result['first'] or 'all',result['last']])
    writer.writerow(['Recorded since',result['first_day'] or 'no records'])
    keys=['starts','completions','active_browsers','exam_starts','practice_starts','exam_completions','switched_completions','average_seconds','abandoned']
    writer.writerow(['Section','Name',*keys])
    writer.writerow(['Totals','All',*[result['totals'][k] for k in keys]])
    # Prefix text that could otherwise be interpreted as spreadsheet formulas.
    for section in ('courses','papers'):
        for row in result[section]:
            name=row['name'] or ''
            if name.lstrip().startswith(('=','+','-','@')):name="'"+name
            writer.writerow([section,name,*[row[k] for k in keys]])
    return out.getvalue()
