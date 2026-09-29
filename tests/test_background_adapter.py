import importlib
from fakeredis import FakeRedis


def test_celery_drain_reuses_pipeline_and_releases_lease(app,monkeypatch):
    monkeypatch.setenv('CELERY_BROKER_URL','redis://test.invalid/1')
    monkeypatch.setattr('backend.create_app',lambda:app)
    module=importlib.import_module('backend.celery_app')
    r=FakeRedis();events=[]
    monkeypatch.setattr('backend.acquisition.download_pending',lambda *a,**kw:events.append(('download',kw)))
    monkeypatch.setattr('backend.ingestion.work_once',lambda:events.append(('process',{})) or True)
    assert module.drain_one(app,r)
    assert events==[('download',{'workers':1,'limit':1}),('process',{})]
    assert module.drain_one(app,r)  # The lease must be released after success.
    lock=r.lock('pyq:ingestion:drain',timeout=1750);assert lock.acquire(blocking=False)
    assert not module.drain_one(app,r)  # A duplicate tick cannot process concurrently.
    lock.release()
