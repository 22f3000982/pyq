# Production stabilization — 28 September 2026

Status: source fixes and isolated acceptance verified. NOT deployed or declared production-complete.
Base GitHub commit: e469acdb719ddc730f2d582e380ce49ab995a481.
The latest uploaded ZIP matched that commit exactly before edits.

## Findings and fixes

- **Catalog/dropdowns:** the shared catalog loader waited for `/courses?limit=100`, which performed three additional queries per course. The live request took 20.08 seconds; `/metadata` returned successfully. This explains prolonged empty controls; a permanent empty catalog/authentication failure was not reproduced. Batched aggregates now replace the N+1 queries. `/api/catalog` supplies the complete dynamic course/exam/term catalog in one response. Upload controls show loading, a useful error and retry. Catalog import refreshes cached options.
- **Mathematical content:** live Deep Learning JSON and uploaded source records contain the actual formula image tokens, including the function and initial point; formulas were not lost from text serialization. `QuestionContent` hid failed images, leaving missing expressions. The component now preserves image positions and shows an explicit retryable unavailable indicator instead of silently removing content. Existing KaTeX handling for explicit inline/display delimiters is retained, with regressions for fractions, Greek letters, subscripts and matrices. No formulas or answer keys were generated or manually replaced.
- **Private images:** attempt responses generated cross-origin R2 presigned URLs while CSP allowed only same-origin images. They also expired during long exams. Questions now use the existing authenticated same-origin image proxy, with private browser caching and conditional responses. No bucket credentials or signed URLs are sent in question payloads. Private buckets remain private. Source aspect ratio and source layout sizing are retained.
- **Missing cloud assets:** read-only listing with the newly attached credentials succeeded but found **0 objects in pyq-pdfs and 0 in pyq-images**. Code cannot display bytes absent from those configured buckets. The existing `scripts/sync_r2.py` now verifies the current PostgreSQL manifest and both buckets before writes, supports `--dry-run` and `--source-dir`, and uploads only missing referenced assets through the existing immutable storage layer. Existing matching objects are read/verified, not re-uploaded. It never changes credentials or `.env`. No cloud upload was run here because direct Supabase connectivity failed.
- **Navigation:** each navigation previously waited for a question GET and a visited-state POST; text saving also blocked navigation. An owner-authorized bundle endpoint loads all question content once, excluding exam answers/explanations. Next/Previous and palette updates use client state. A serialized asynchronous save queue prevents overlapping writes, journals per-question pending responses, survives reload/offline transitions, and drains before submission/mode changes. Next-question assets are prefetched. Timer/metadata updates never replace the active input.
- **API efficiency:** paper summaries use aggregate marks/count/key queries and batched progress/download lookups. Course summaries use batched aggregates. Starting papers and listing public questions eager-load options/images. Creating question image URLs no longer queries storage/image metadata per question. Paper detail pages avoid unrelated homepage/statistics requests.
- **Production configuration:** production now rejects explicit SQLite and local-storage fallback, including misconfigured environments. Render web and worker explicitly set `APP_ENV=production`. Existing non-root Docker user and writable `/data/uploads`/instance setup are retained. Storage/SQL failures return sanitized errors. Docker build context excludes `.git` and private environment/data files.
- **Bounded ingestion:** `--retry-failed` now selects failed papers only; completed/canonical papers are skipped. Candidate lookup is batched. Existing extraction and per-paper ingestion state remain in place; no whole-file migration checkpoint is introduced.
- **Catalog cache freshness:** successful uploads/imports invalidate catalog cache, and adding a term refreshes the mounted upload form. Catalog caching is limited to shared catalog data; answers/progress/bookmarks are not shared across users.
- **Test discovery:** `pytest.ini` limits unit/regression collection to `tests/`, avoiding automatic execution of the standalone real-data acceptance script during test collection.

## Verification

- Complete backend suite after primary fixes: **101 passed** (77.04 seconds).
- Later storage/sync changes: **18 affected tests passed**, including two additional preflight/idempotency regressions. The final backend collection contains 103 tests; the full 101-test run plus affected later tests is the evidence, not a claim that all 103 were rerun together.
- Later bounded-ingestion adjustment: **1 affected test passed**.
- Frontend component/regression suite: **23 passed**. After the final catalog refresh change, **11 affected tests passed**, including two new cache regressions (25 component tests in the final collection).
- Frontend utility tests: **3 passed**.
- Vite production build: **passed**.
- Regression checks cover bounded catalog queries, complete catalog options, exam bundle authorization/no keys, source formula placeholders, private image auth/cache/304/missing behavior, production fallback rejection, unresolved/offline saves, fast navigation, NAT refresh persistence, single timeout submit, source math rendering and retryable missing notation.
- Five real papers: Practice, Exam, image proxy reads, source-key server scoring, result/review, retake and one latest progress row all passed on an **isolated SQLite copy**. No source PDF was reprocessed. All five live public question payloads matched source copy text/options/marks/type/image metadata. See `STABILIZATION-FIVE-PAPERS.json`.

| Course | Paper ID | Exam | Term | Questions | Marks | With keys | With images |
|---|---:|---|---|---:|---:|---:|---:|
| Deep Learning | 13 | End Term | May 2026 | 20 | 50 | 20 | 20 |
| Software Engineering | 1 | Quiz 2 | May 2026 | 27 | 100 | 27 | 10 |
| Game Theory and Strategy | 50 | Quiz 1 | May 2026 | 16 | 25 | 16 | 6 |
| Managerial Economics | 54 | Quiz 1 | May 2026 | 22 | 25 | 22 | 6 |
| AI: Search Methods for Problem Solving | 7 | Quiz 1 | May 2026 | 26 | 25 | 26 | 18 |

The numbers 13/1/50/54/7 in the supplied brief are paper IDs, not question counts.

## Live measurements and remaining limits

Read-only production requests before deployment of these fixes:
- `/healthz`: 200, 5.82 s.
- `/api/metadata`: 200, 6.12 s.
- `/api/courses?limit=100`: 200, 20.08 s.
- `/api/papers/13`: 200, 5.53 s.
- `/api/papers/13/questions?limit=100`: 200, 10.12 s.

These are observed request timings from this environment, not browser-local timings or post-fix production benchmarks. All five production paper/detail/question reads succeeded.

Direct Supabase failed DNS resolution in this execution environment. Live PostgreSQL table counts, new-code tests against Supabase, private production image delivery and authenticated live student flows were therefore not verified. Production data was not migrated, reset, deleted or modified. R2 objects were not modified. The original uploaded SQLite remained byte-for-byte unchanged.

GitHub read/clone worked. A push preflight failed: `could not read Username for 'https://github.com': No such device or address`. No credentials were requested or embedded. Changes are committed locally and delivered as source.

A real Chromium browser could not be installed: the browser download was invalid/truncated (`End of central directory record signature not found`). DOM/component tests ran, but no new-code visual browser end-to-end success is claimed. Docker is unavailable in this environment; Dockerfile/configuration inspection passed, but a Docker build was not run.

Do not equate the passing isolated tests with a complete production rollout: the empty configured R2 buckets and deployment access remain operational blockers.

## Files changed

- `.dockerignore`
- `DEPLOY-STABILIZED.md`
- `backend/__init__.py`
- `backend/api.py`
- `backend/exam_api.py`
- `backend/storage.py`
- `bulk_ingest.py`
- `docs/PRODUCTION-STABILIZATION.md`
- `docs/STABILIZATION-FIVE-PAPERS.json`
- `frontend/dist/assets/index-Cx-jqwmw.js`
- `frontend/dist/assets/index-DTtFpaXr.js`
- `frontend/dist/index.html`
- `frontend/src/Admin.vue`
- `frontend/src/Catalog.vue`
- `frontend/src/Exam.vue`
- `frontend/src/QuestionContent.vue`
- `frontend/src/Upload.vue`
- `frontend/src/api.js`
- `frontend/tests/catalog-cache.spec.js`
- `frontend/tests/components.spec.js`
- `frontend/tests/nat.spec.js`
- `frontend/tests/progress.spec.js`
- `frontend/tests/stability.spec.js`
- `pytest.ini`
- `render.yaml`
- `scripts/sync_r2.py`
- `tests/test_bulk_ingest.py`
- `tests/test_database_config.py`
- `tests/test_production_stability.py`
- `tests/test_storage_r2.py`
