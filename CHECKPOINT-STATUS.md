# Performance checkpoint — STOPPED at user request

This ZIP contains changed/new source files only, relative to the current PYQ-Studio-Final-App project root.
It is a work-in-progress checkpoint, NOT a verified production release.
Do not overwrite your live deployment with this checkpoint yet.
No production database, R2 objects, deployment settings or credentials were changed.

## Implemented in source
- Server-Timing and sanitized slow-request logging: application, SQL execution/query count, ensure_local, send_asset, R2 download, disk writes and cache hit/miss.
- Verified ensure_local already returns an existing local file without downloading from R2. Kept this behavior.
- Answer response calculated before commit and returned only after successful commit, avoiding post-commit reloads.
- Web-request expiration/cleanup scoped to the current user; background cleanup remains global.
- Eager paper metadata, shared paper snapshots and bounded public question pagination.
- Configurable private signed image URLs, batched paths for older snapshots, authenticated redirect refresh, scoped image CSP.
- Optional CDN manifest allowlist with content-hashed image keys; unlisted assets retain the authenticated proxy. No bucket made public.
- Controlled per-process PostgreSQL pool settings.
- Three additive hot-path indexes in migration e51a9c320002; NOT applied to production.
- Redis content cache for catalog/paper metadata/question snapshots with commit-triggered invalidation, bounded lock waiting and 60-second default TTL. Student state/progress is not shared cached.
- Combined attempt bootstrap; frontend reuses new-attempt payload, reducing startup HTTP round trips. Next/Previous remains local with background saves.
- Signed-image fallback, versioned JS/CSS cache policy, public-content gzip; session/answer responses excluded from compression.
- Gunicorn gthread configuration, environment-controlled workers/threads/pools and timeout. Defaults are provisional, NOT load-tested capacity recommendations.
- Optional Celery adapter around existing ingestion pipeline; durable PostgreSQL queue retained, bounded one-file acquisition per tick, singleton drain lease, no catalog-wide import started.
- bulk_ingest.py --enqueue, and automatic queue-only behavior when CELERY_BROKER_URL is configured.
- Deployment config templates updated for Redis cache, CDN/image delivery, and Celery broker variables in `.env.example`, `compose.yaml`, and `render.yaml`.
- Local ingestion worker now prioritizes uploaded `QUEUED` PDFs and limits catalog acquisition to one file per tick, preventing catalog backlog starvation. Verified the previously stuck `iesc107.pdf` upload advanced to `PARTIAL` with no error.
- Upload deduplication now verifies the canonical asset exists before reusing it; re-uploading a PDF whose old local asset disappeared stores fresh bytes instead of creating a broken `DUPLICATE` record. Retry now gives a clear re-upload message when recovery bytes are unavailable.
- PDF upload limit is aligned with the existing request limit at 110 MB, and CSP now permits the frontend's data-font assets. The local web server was restarted with this configuration.
- Large-PDF validation confirmed `Class_9_Work_and_Energy_12_Page_Notes.pdf` is 12-page image-only content with zero extracted text; OCR is unavailable locally. The ingestion error now explains that this is not a reliable text-based PYQ input and recommends a text PDF or OCR-enabled environment.
- Ingestion worker error handling now survives transient PostgreSQL/DNS outages without crashing while persisting an error; after the Supabase pooler recovered, the read-only database check passed again.
- Home feed now appends the newest available uploaded papers to the curated demo-paper cards, so completed uploads are visible from the home screen without requiring a course search.

## Evidence completed
Baseline: isolated SQLite fixture (2 questions, NOT production latency):
- Attempt start: 16 SQL statements before; 13 after early optimization.
- Answer save: 6 before; 4 after early optimization in same fixture.
- Existing local image cache hit: no R2 download.
- Earlier affected backend run: 52 passed (performance paths, scoring, progress, storage, catalog stability, bulk selection).
- Latest focused backend run: 8 passed (7 performance tests plus Celery adapter test).
- Latest full frontend run: 24 passed, 1 failed.
- Latest focused frontend run after adding bootstrap tests: 7 passed, 1 failed.
- Deployment config groundwork updated: Redis cache, CDN/image delivery, and Celery broker vars are now present in the env templates and deployment manifests.
- Frontend production build completed after the user's stop request.
- Frontend non-retry validation: 18 tests passed (catalog cache, components, NAT, progress and utilities).
- Backend validation after installing requirements-test.txt: 110 passed, 1 failed because Windows kept the image file open while the existing test attempted to unlink it; this is an environment/file-handle failure, not an assertion failure.
- Targeted remaining backend validation: 23 passed, covering Redis/fakeredis cache, Celery adapter, migration/index configuration, database configuration, and five-paper upload flows.
- Frontend validation excluding the deferred retry spec: 23 passed across all 6 remaining test files.
- render.yaml parsed successfully as valid YAML.
- Read-only configured PostgreSQL check passed: `SELECT 1` succeeded.
- Read-only configured R2 check passed: authenticated bucket access succeeded.
- Configured PostgreSQL was upgraded to migration `e51a9c320002` (repository head). All three additive indexes are present: `ix_question_paper_status_id`, `ix_attempt_user_status`, and `ix_ingestion_file_status_id`.
- Post-migration read-only EXPLAIN completed. The small current dataset still selects the older question index and a sequential scan for the attempt query; the new composite indexes are available for larger staging data.
- Rollback-safe five-paper PostgreSQL acceptance passed for papers 13, 1, 50, 54, and 7: Practice, Exam, NAT persistence where applicable, scoring, review, retake latest progress, and timer timeout all passed.
- Added dependency-free `scripts/load_test.py` for repeatable concurrent smoke checks.
- Local Flask smoke run completed against `/healthz`: 50 users produced 19/50 HTTP 200 responses, 100 users 44/100, 150 users 44/150, and 200 users 0/200; failures were local SQLite/health 503 responses and cumulative rate-limit 429 responses. These are diagnostic local results, not production capacity evidence.
- Redis tested with fakeredis (including Lua support), not a deployed Redis service.
- Celery adapter tested with isolated fixtures; no real broker/worker service launched.

## Deferred item — skipped at user request
frontend/tests/stability.spec.js:
  keeps offline responses across navigation and restores them after remount
Expected pending-response sessionStorage entry to be cleared after Retry; it remained populated.
Latest retry/open changes have NOT resolved the failing test. The user asked to skip this item; do not claim offline retry/remount stability until it is revisited.

## Live blockers and pending work
- Frontend offline retry/remount regression remains unresolved and was explicitly deferred by the user; deployment claim must remain limited accordingly.
- Read-only configured PostgreSQL check passes and migration `e51a9c320002` is applied.
- Read-only configured R2 authentication now passes.
- No Redis/Celery broker URL or CDN custom domain/approved image manifest is configured; no separate staging DB target is identified.
- Cannot verify remote timing, cloud configuration or production integration from here.
- CDN public-object preparation/publication and immutable headers are NOT implemented/applied. CDN allowlist support is configuration groundwork only.
- No real 50/100/200/300/500 concurrent-student load test has run; no 500-user capacity claim.
- Load-test harness is now available at `scripts/load_test.py`; realistic staging load runs and full infrastructure monitoring remain pending.
- Production Redis/Celery deployment configuration, isolated staging tests, region comparison, EXPLAIN/query plans, final pool/worker tuning and rollback rehearsal pending.
- Final frontend build is complete; five-paper rollback-safe flow regression passed against the configured PostgreSQL database.
- Production deploy and rollback rehearsal remain pending.
- Extraction/parser logic and five verified PDFs were not reprocessed.
- Existing parser keeps per-question SAVEPOINTs to isolate partial extraction failures; no bulk-parser rewrite performed.

## Resume order
1. Verify shared Redis/cache invalidation and Celery with actual isolated services.
2. Configure CDN domain/manifest and validate direct image delivery.
3. Run staged 50/100/150/200-user load tests with monitoring and tune capacity.
4. Deploy with rollback rehearsal; revisit the deferred offline retry regression before declaring full frontend stability.

## Source/config notes
- Source overlay only: frontend/dist is intentionally NOT included, since it was not rebuilt.
- Preserve existing .env, uploads, instance databases and local backups.
- requirements.txt adds celery==5.6.2; requirements-test.txt adds fakeredis[lua]==2.34.1.
- New config: REDIS_URL, CACHE_NAMESPACE, CONTENT_CACHE_TTL,
  IMAGE_DELIVERY=proxy|signed|cdn, IMAGE_CDN_BASE_URL, IMAGE_CDN_MANIFEST,
  DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_TIMEOUT,
  WEB_CONCURRENCY, GUNICORN_THREADS, GUNICORN_TIMEOUT,
  CELERY_BROKER_URL, CELERY_QUEUE_NAMESPACE.
- Keep IMAGE_DELIVERY=proxy until direct delivery is tested with your actual endpoint/CSP.
- Redis cache invalidation failure falls back to bounded TTL; strict cross-service revision guarantees and outage testing remain to be reviewed.
- Do not run legacy ingestion worker and Celery drain concurrently until coordinated deployment is verified.
- Docker now reads gunicorn.conf.py. Existing GUNICORN_CMD_ARGS can override some settings; reconcile these during deployment.
