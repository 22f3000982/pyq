"""Permanent minimal analytics; reads and aggregation only in the admin dashboard.

One insert/update is piggybacked on the existing transaction, in an isolated
savepoint. No daemon queue, additional browser requests, or stored answer choices.
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
from sqlalchemy import func, case, select, Integer, cast, or_, values as sql_values, column
from .models import db, AnalyticsEvent, AnalyticsQuestionDay

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
                exam_name=paper.exam_type.name,device=device,browser_key=browser,initial_mode=paper and request.get_json().get('mode','practice'))

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
        values['exam_name']=e.get('exam_name')
        # Scores are comparable only for unassisted exams with reliable grading.
        values['score_percent']=(attempt.result or {}).get('percentage') if attempt.submitted_at is not None and e.get('initial_mode')=='exam' and attempt.mode=='exam' and not e.get('assisted') else None
        values.update(key=event_key(attempt),started_at=attempt.started_at,start_day=day(attempt.started_at),
                      expires_at=attempt.expires_at,automatic=automatic,
                      completed_at=attempt.submitted_at,completion_mode=('assisted_exam' if e.get('assisted') and attempt.mode=='exam' else attempt.mode) if attempt.submitted_at is not None else None)
        stmt=insert(table).values(**values)
        if attempt.submitted_at is None:
            stmt=stmt.on_conflict_do_nothing(index_elements=['key'])
        else:
            stmt=stmt.on_conflict_do_update(index_elements=['key'],set_={k:stmt.excluded[k] for k in
                ('completed_at','completion_mode','automatic','expires_at','score_percent')},where=table.c.completed_at.is_(None))
        rows=question_totals(attempt) if attempt.submitted_at is not None else []
        with db.session.begin_nested():
            if dialect=='postgresql' and rows:
                # Same network round-trip as the previous event-only writer.
                db.session.execute(completion_statement(stmt,rows))
            else:
                result=db.session.execute(stmt)
                if rows and result.rowcount:db.session.execute(question_upsert(insert,rows))
    except Exception:
        current_app.logger.warning('Analytics write failed; main learner transaction retained',exc_info=True)



def question_totals(attempt):
    # One bounded bulk UPSERT after the event's first completion wins. Existing
    # loaded/graded snapshots are reused; no per-question query or browser request.
    from .ai_solutions import version
    e=attempt.analytics_context
    mode='exam' if e.get('initial_mode')=='exam' and attempt.mode=='exam' and not e.get('assisted') else 'practice'
    rows=[]
    for item in attempt.items:
        if item.question_id is None:continue
        counts={k:int(item.outcome==k.upper()) for k in ('correct','partial','incorrect','skipped','ungraded')}
        rows.append(dict(day=day(attempt.started_at),paper_key=e['paper_key'],question_id=item.question_id,
                         version=version(item.snapshot),mode=mode,number=str(item.snapshot.get('number',''))[:40],**counts))
    return rows

def question_upsert(insert,rows):
    table=AnalyticsQuestionDay.__table__
    stmt=insert(table).values(rows)
    stmt=stmt.on_conflict_do_update(index_elements=['day','paper_key','question_id','version','mode'],
        set_={k:table.c[k]+stmt.excluded[k] for k in ('correct','partial','incorrect','skipped','ungraded')})
    return stmt

def completion_statement(event_statement,rows):
    from sqlalchemy.dialects.postgresql import insert
    table=AnalyticsQuestionDay.__table__;names=list(rows[0])
    completed=event_statement.returning(AnalyticsEvent.key).cte('completed_event')
    outcomes=sql_values(*[column(k,table.c[k].type) for k in names],name='question_outcomes').data([tuple(row[k] for k in names) for row in rows])
    select_rows=select(*[outcomes.c[k] for k in names]).where(select(completed.c.key).exists())
    stmt=insert(table).from_select(names,select_rows,include_defaults=False)
    return stmt.on_conflict_do_update(index_elements=['day','paper_key','question_id','version','mode'],set_={k:table.c[k]+stmt.excluded[k] for k in ('correct','partial','incorrect','skipped','ungraded')})


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


def report(period,start=None,end=None,now=None,course=None,mode=None):
    now=time.time() if now is None else now
    first,last=date_range(period,start,end,now)
    if course is not None and (not isinstance(course,str) or len(course)>64):raise ValueError('Invalid course filter')
    if mode not in (None,'','exam','practice'):raise ValueError('Choose exam or practice')
    E=AnalyticsEvent
    score=case(((E.completion_mode=='exam')&(E.initial_mode=='exam'),E.score_percent),else_=None)
    cols=[func.count(E.key).label('starts'),func.count(E.completed_at).label('completions'),
          func.count(func.distinct(E.browser_key)).label('active_browsers'),
          func.sum(case((E.initial_mode=='exam',1),else_=0)).label('exam_starts'),
          func.sum(case((E.initial_mode=='practice',1),else_=0)).label('practice_starts'),
          func.sum(case(((E.initial_mode=='exam')&(E.completion_mode=='exam'),1),else_=0)).label('exam_completions'),
          func.sum(case(((E.initial_mode=='exam')&(E.completion_mode.in_(['practice','assisted_exam'])),1),else_=0)).label('switched_completions'),
          func.sum(case((E.automatic.is_(True),1),else_=0)).label('automatic'),
          func.sum(case((E.completed_at.is_(None)&(E.expires_at<=now),1),else_=0)).label('abandoned'),
          func.avg(E.completed_at-E.started_at).label('average_seconds'),
          func.avg(score).label('average_score'),func.count(score).label('scored_exams')]
    def scoped(query,lo,hi):
        query=query.filter(E.start_day<=hi)
        if lo:query=query.filter(E.start_day>=lo)
        if course:query=query.filter(E.course_key==course)
        if mode:query=query.filter(E.initial_mode==mode)
        return query
    def metrics(row):
        m=dict(row._mapping)
        for k in ('exam_starts','practice_starts','exam_completions','switched_completions','automatic','abandoned'):m[k]=m[k] or 0
        for k in ('average_seconds','average_score'):m[k]=round(m[k],1) if m[k] is not None else None
        m['completion_rate']=round(100*m['completions']/m['starts'],1) if m['starts'] else None
        m['dropoff_rate']=round(100*m['abandoned']/m['starts'],1) if m['starts'] else None
        m['active']=m['starts']-m['completions']-m['abandoned']
        return m
    q=scoped(db.session.query(*cols),first,last)
    def groups(column):return [metrics(r) for r in q.add_columns(column.label('name')).group_by(column).order_by(func.count(E.key).desc(),column).limit(50)]
    papers=[metrics(r) for r in q.add_columns(E.paper_key.label('key'),func.max(E.paper_name).label('name')).group_by(E.paper_key).order_by(func.count(E.key).desc(),E.paper_key).limit(50)]
    courses=[metrics(r) for r in q.add_columns(E.course_key.label('key'),func.max(E.course_name).label('name')).group_by(E.course_key).order_by(func.count(E.key).desc(),E.course_key).limit(50)]
    first_day=db.session.query(func.min(E.start_day)).scalar()
    chart_start=max(first or first_day or last,(datetime.strptime(last,'%Y-%m-%d').date()-timedelta(days=89)).isoformat())
    daily={r.start_day:metrics(r) for r in q.add_columns(E.start_day).filter(E.start_day>=chart_start).group_by(E.start_day)}
    trend=[];cursor=datetime.strptime(chart_start,'%Y-%m-%d').date();finish=datetime.strptime(last,'%Y-%m-%d').date()
    while cursor<=finish:
        label=cursor.isoformat();trend.append(dict(day=label,**daily.get(label,dict(starts=0,completions=0,exam_starts=0,practice_starts=0,active_browsers=0))))
        cursor+=timedelta(days=1)
    totals=metrics(q.one())
    # Browser retention is platform-wide history for the currently selected cohort.
    history=db.session.query(E.browser_key.label('browser'),func.min(E.start_day).label('first'),func.count(func.distinct(E.start_day)).label('days')).filter(E.start_day<=last).group_by(E.browser_key).subquery()
    cohort=scoped(db.session.query(E.browser_key),first,last).distinct().subquery()
    returning=db.session.query(func.count()).select_from(cohort).join(history,history.c.browser==cohort.c.browser_key).filter(or_(history.c.days>1,history.c.first<(first or first_day or last))).scalar()
    totals.update(returning_browsers=returning,new_browsers=totals['active_browsers']-returning)
    # UTC epoch + IST offset yields a portable hour/week-day expression on SQLite/Postgres.
    local_days=cast(func.floor((E.started_at+19800)/86400),Integer)
    hour=cast(func.floor((E.started_at+19800)/3600),Integer)%24
    weekday=(local_days+3)%7
    heatmap=[dict(weekday=int(r.weekday),hour=int(r.hour),starts=r.starts) for r in scoped(db.session.query(weekday.label('weekday'),hour.label('hour'),func.count().label('starts')),first,last).group_by(weekday,hour)]
    week=cast(func.floor((local_days+3)/7),Integer)
    weekly=[dict(week_start=(datetime(1970,1,1).date()+timedelta(days=int(r.week)*7-3)).isoformat(),active_browsers=r.active_browsers,starts=r.starts,completions=r.completions) for r in scoped(db.session.query(week.label('week'),func.count(func.distinct(E.browser_key)).label('active_browsers'),func.count().label('starts'),func.count(E.completed_at).label('completions')),chart_start,last).group_by(week).order_by(week)]
    comparison=None
    if first:
        lo=datetime.strptime(first,'%Y-%m-%d').date();hi=datetime.strptime(last,'%Y-%m-%d').date();span=(hi-lo).days+1
        previous_first=(lo-timedelta(days=span)).isoformat();previous_last=(lo-timedelta(days=1)).isoformat()
        previous=metrics(scoped(db.session.query(*cols),previous_first,previous_last).one())
        comparison=dict(first=previous_first,last=previous_last,totals=previous,change={k:round(100*(totals[k]-previous[k])/previous[k],1) if previous[k] else None for k in ('starts','completions','active_browsers')})
    buckets=[('Below 25%',None,25),('25–49%',25,50),('50–74%',50,75),('75–100%',75,None)]
    distribution=[]
    for label,lo,hi in buckets:
        column=score.isnot(None)
        if lo is not None:column=column&(score>=lo)
        if hi is not None:column=column&(score<hi)
        distribution.append((label,func.sum(case((column,1),else_=0)).label('bucket_'+str(len(distribution)))))
    bucket_row=scoped(db.session.query(*[c for _,c in distribution]),first,last).one()
    score_distribution=[dict(name=label,count=bucket_row[i] or 0) for i,(label,_) in enumerate(distribution)]
    attention=content_attention(course,papers)
    attention['questions']=question_attention(first,last,course,mode)
    attention['low_score_papers']=[p for p in sorted(papers,key=lambda r:r['average_score'] if r['average_score'] is not None else 101) if p['scored_exams']>=20 and p['average_score'] is not None and p['average_score']<50][:10]
    from .models import Course
    names={r.course_key:r.name for r in db.session.query(E.course_key,func.max(E.course_name).label('name')).group_by(E.course_key)}
    names.update({c.code or str(c.id):c.name for c in Course.query.all()})
    options=[dict(key=k,name=v) for k,v in sorted(names.items(),key=lambda item:item[1].casefold())]
    return dict(period=period,first=first,last=last,timezone='Asia/Kolkata',totals=totals,papers=papers,courses=courses,
                devices=groups(E.device),trend=trend,weekly=weekly,heatmap=heatmap,comparison=comparison,score_distribution=score_distribution,
                attention=attention,course_options=options,filters=dict(course=course or '',mode=mode or ''),first_day=first_day,generated_at=now,
                learning_recorded_since=db.session.query(func.min(E.start_day)).filter(E.score_percent.isnot(None)).scalar())


_content_cache={}
def content_attention(course,popular):
    """Current content health is independent of date/mode, cached for two minutes."""
    from copy import deepcopy
    from .models import Paper,Course,Question,ContentReport
    from .study_pages import solution_coverage
    key=(id(current_app._get_current_object()),course)
    now=time.time()
    with _lock:hit=_content_cache.get(key)
    if hit and now-hit[0]<120:result=deepcopy(hit[1])
    else:
        query=Paper.query.join(Course).filter(Paper.status!='ARCHIVED')
        if course:query=query.filter((Course.code==course) if not course.isdigit() else or_(Course.code==course,Course.id==int(course)))
        from sqlalchemy.orm import selectinload
        all_papers=query.options(selectinload(Paper.course)).all();ids=[p.id for p in all_papers];coverage=solution_coverage(ids)
        rows={p.identity:dict(id=p.id,name=p.name,course=p.course.name,**coverage[p.id]) for p in all_papers if p.id in coverage}
        questions=sum(v['total'] for v in coverage.values());published=sum(v['published'] for v in coverage.values())
        reports=ContentReport.query.join(Question,Question.id==ContentReport.question_id).filter(ContentReport.status=='OPEN')
        if ids:reports=reports.filter(Question.paper_id.in_(ids))
        else:reports=reports.filter(False)
        open_count=reports.count()
        open_rows=[dict(id=r.id,question_id=r.question_id,number=number,paper_id=pid,issue=r.issue) for r,number,pid in reports.with_entities(ContentReport,Question.number,Question.paper_id).order_by(ContentReport.created_at.desc()).limit(10)]
        result=dict(coverage=dict(questions=questions,published=published,percent=round(100*published/questions,1) if questions else None),catalog=rows,open_reports=open_count,reports=open_rows,content_generated_at=now)
        with _lock:
            if len(_content_cache)>=64:_content_cache.clear()
            _content_cache[key]=(now,deepcopy(result))
    catalog=result.pop('catalog');result['unsolved']=[]
    for p in popular:
        current=catalog.get(p['key'])
        if current and current['published']<current['total']:
            result['unsolved'].append(dict(**current,starts=p['starts'],missing=current['total']-current['published']))
    result['unsolved']=result['unsolved'][:10]
    return result


def question_attention(first,last,course,mode):
    from .models import Question,Paper,Course
    from sqlalchemy.orm import selectinload
    from .engine import question_snapshot
    from .ai_solutions import version
    if mode=='practice':return [] # Practice reveals can bias question accuracy.
    Q=AnalyticsQuestionDay
    query=db.session.query(Q.question_id,Q.paper_key,Q.version,func.max(Q.number).label('number'),func.sum(Q.correct).label('correct'),func.sum(Q.partial).label('partial'),func.sum(Q.incorrect).label('incorrect')).filter(Q.mode=='exam',Q.day<=last)
    if first:query=query.filter(Q.day>=first)
    if course:
        identities=db.session.query(Paper.identity).join(Course).filter((Course.code==course) if not course.isdigit() else or_(Course.code==course,Course.id==int(course)))
        query=query.filter(Q.paper_key.in_(identities))
    graded=func.sum(Q.correct+Q.partial+Q.incorrect)
    candidates=query.group_by(Q.question_id,Q.paper_key,Q.version).having(graded>=20).having(func.sum(Q.correct)*100<graded*30).order_by((func.sum(Q.correct)*1.0/graded),graded.desc()).limit(100).all()
    questions={q.id:q for q in Question.query.options(selectinload(Question.options),selectinload(Question.images),selectinload(Question.paper)).filter(Question.id.in_([r.question_id for r in candidates]),Question.status=='AVAILABLE')}
    rows=[]
    for r in candidates:
        q=questions.get(r.question_id)
        if q is None or version(question_snapshot(q))!=r.version:continue
        n=r.correct+r.partial+r.incorrect
        rows.append(dict(question_id=q.id,paper_id=q.paper_id,paper=q.paper.name,number=q.number,graded=n,accuracy=round(100*r.correct/n,1),partial=r.partial))
        if len(rows)==10:break
    return rows


def cached_report(period,start=None,end=None,course=None,mode=None):
    # No report/cache work on learner actions. Independent caches per filter scope.
    key=(id(current_app._get_current_object()),period,start,end,course,mode)
    now=time.time()
    with _lock:
        hit=_cache.get(key)
        if hit and now-hit[0]<30:return hit[1]
    result=report(period,start,end,course=course,mode=mode)
    with _lock:
        if len(_cache)>=64:_cache.clear()
        _cache[key]=(now,result)
    return result


def csv_report(result):
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['MauryaHub usage analytics','IST',result['first'] or 'all',result['last']])
    writer.writerow(['Recorded since',result['first_day'] or 'no records'])
    writer.writerow(['Filters','Course',(result.get('filters') or {}).get('course',''),'Mode',(result.get('filters') or {}).get('mode','')])
    keys=['starts','completions','active_browsers','exam_starts','practice_starts','exam_completions','switched_completions','average_seconds','abandoned','average_score','scored_exams']
    writer.writerow(['Section','Name',*keys])
    writer.writerow(['Totals','All',*[result['totals'][k] for k in keys]])
    # Prefix text that could otherwise be interpreted as spreadsheet formulas.
    for section in ('courses','papers'):
        for row in result[section]:
            name=row['name'] or ''
            if name.lstrip().startswith(('=','+','-','@')):name="'"+name
            writer.writerow([section,name,*[row[k] for k in keys]])
    writer.writerow(['Current content coverage',result.get('attention',{}).get('coverage',{}).get('published',0),result.get('attention',{}).get('coverage',{}).get('questions',0)])
    return out.getvalue()
