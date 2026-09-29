"""Request timings without SQL text, parameters, user IDs or credential URLs."""
import time
from contextlib import contextmanager
from flask import g, has_request_context, request
from sqlalchemy import event


@contextmanager
def span(name):
    start = time.perf_counter()
    try:
        yield
    finally:
        if has_request_context() and hasattr(g, 'perf'):
            g.perf[name] = g.perf.get(name, 0) + (time.perf_counter() - start) * 1000


def count(name):
    if has_request_context() and hasattr(g, 'perf'):
        g.perf[name] = g.perf.get(name, 0) + 1


def install(app, db):
    @app.before_request
    def begin():
        g.perf = {'start': time.perf_counter(), 'sql': 0, 'queries': 0}

    def before(conn, cursor, statement, parameters, context, many):
        context._pyq_started = time.perf_counter()

    def after(conn, cursor, statement, parameters, context, many):
        if has_request_context() and hasattr(g, 'perf'):
            g.perf['sql'] += (time.perf_counter() - context._pyq_started) * 1000
            g.perf['queries'] += 1

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', before)
        event.listen(db.engine, 'after_cursor_execute', after)

    @app.after_request
    def finish(response):
        metrics = getattr(g, 'perf', None)
        if metrics is None:
            return response
        elapsed = (time.perf_counter() - metrics['start']) * 1000
        values = [f'app;dur={elapsed:.2f}', f'sql;dur={metrics["sql"]:.2f}',
                  f'queries;desc="{metrics["queries"]}"']
        for name in ('ensure_local', 'r2_download', 'disk_write', 'send_asset'):
            if name in metrics:
                values.append(f'{name};dur={metrics[name]:.2f}')
        for name in ('asset_hit', 'asset_miss', 'cache_hit', 'cache_miss', 'cache_error'):
            if name in metrics:
                values.append(f'{name};desc="{metrics[name]}"')
        response.headers['Server-Timing'] = ', '.join(values)
        if elapsed >= app.config.get('SLOW_REQUEST_MS', 750):
            # Route template only: no actual path, query strings, body or SQL.
            route = str(request.url_rule) if request.url_rule else 'unmatched'
            app.logger.warning('slow_request route=%s method=%s status=%s app_ms=%.1f sql_ms=%.1f queries=%d',
                               route, request.method, response.status_code, elapsed, metrics['sql'], metrics['queries'])
        return response
