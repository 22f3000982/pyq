# PYQ Studio: consolidated database and R2 setup

Use the existing `PYQ-Studio-Final-App` folder. This update does not create another
application, overwrite SQLite, delete PDFs, or process the remaining catalog.
#
## Windows

1. Stop START.cmd/web/worker with Ctrl+C.
2. Run `MIGRATE.cmd` once from this app folder. It backs up the existing SQLite
   database, runs the guarded Supabase migration and verification gates, and never
   overwrites the original database or local assets.
3. If R2 is pending, set its private values in this app's `.env`, then run
   `FINISH-SETUP.cmd` in this SAME app folder. It verifies and syncs R2 without
   deleting local originals. You do not need another ZIP.
5. After `DATABASE AND R2 READY`, use `START.cmd` and refresh with Ctrl+F5.

Existing admin credentials, courses, questions and PDFs remain in use. Student accounts are no longer required.
The Windows launchers use this folder's `.venv` when present and otherwise invoke
the installed Python launcher; they do not depend on another project folder.

## R2 configuration (only in private .env)

Create private Cloudflare R2 buckets named `pyq-pdfs` and `pyq-images`, with one
Object Read & Write access token scoped to both buckets. Copy the S3 API endpoint,
Access Key ID and Secret Access Key privately; do not paste secrets into chat or
GitHub:

```dotenv
R2_ENDPOINT_URL=https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=YOUR_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY=YOUR_SECRET_ACCESS_KEY
R2_PDF_BUCKET_NAME=pyq-pdfs
R2_IMAGE_BUCKET_NAME=pyq-images
R2_PREFIX=pyq
STORAGE_BACKEND=local
```

Leave STORAGE_BACKEND local initially. FINISH-SETUP uploads the existing PDF/image
files, reads every object back and checks SHA-256, keeps all local originals, then
sets STORAGE_BACKEND=r2. A subsequent run skips objects with identical contents.
Conflicting objects are never silently overwritten. Do not enable public bucket
access; Flask serves assets and retains the existing route authorization checks.
No public URL or frontend R2 credentials are required. PDFs/images use a local
cache that can be rebuilt from R2; database paths remain unchanged.

Before enabling R2, use `python scripts/check_r2.py` for a read-only endpoint and
credential check. It does not edit `.env` or change any object. Run
`scripts/sync_r2.py` only after that check passes.

The normal PDF upload pipeline now writes PDFs to R2, extracts locally, stores
question images in R2, and only then makes successful extracted questions available.
A storage failure is logged and retryable; it cannot silently report successful
processing. Source PDFs and generated images have SHA-256 metadata and verified
sizes. Source page previews can be regenerated from the stored PDF.

Official Cloudflare reference:
https://developers.cloudflare.com/r2/examples/aws/boto3/
https://developers.cloudflare.com/r2/get-started/s3/

## Dependency failure resolved

The previous screenshot stopped at npm dependencies. Dependencies are now pinned
and tested with Node 22.10.0, including compatible Vue test-utils, jsdom, Vitest,
Vite and Vue plugin versions. Strict npm engine validation, component tests,
utility tests and the production build were run with that exact Node version.
On Windows the runner invokes npm-cli.js through node where available, avoiding
.cmd wrapper exit-code ambiguity. Dependency installation is keyed to the lockfile
hash, so an incomplete/old node_modules folder cannot skip the fixed installation.

## Migration safeguards

- Original SQLite gets a read-only backup and is not migrated in place.
- Read-only PostgreSQL SELECT 1 precedes destination operations.
- Development users, attempts, attempt answers, bookmarks, reviews and progress
  are excluded from the disposable migration snapshot. Stable catalog, question,
  asset-reference and ingestion records are preserved; a disabled synthetic owner
  is used only when ingestion batches require their user foreign key.
- Existing Flask-Migrate revisions and normalized models are used.
- Missing stable rows are inserted, identical rows are skipped, destination-only
  rows are preserved, and conflicting stable records stop the run without silent
  overwrites. RLS protects backend tables from direct Data API access.
- Tests use explicit schema-qualified tables in a separate temporary schema.
- If data copy succeeded but a later test failed, the runner can resume from its
  saved stable working snapshot after logical stable-record reconciliation; a
  whole-SQLite physical hash change caused by disposable development activity is
  not a migration blocker.
- Supabase activates only after backend/frontend and five-paper checks pass.
- A successful database migration is not repeated while finishing R2 setup.

Reports: migration-backups/ and storage-reports/. These contain private operational
information and are gitignored. Do not upload backups or private .env to GitHub.

## What has and has not been verified

See docs/READY-VERIFICATION.md. Automated tests use isolated database copies and
stubbed object storage. The five real uploaded papers were exercised with an empty
local asset cache backed by the test object store. Tests do not validate live R2
credentials or remote object state; the setup command performs those checks before
enabling production storage.

## Deployment

The code includes a Dockerfile and existing Flask/Vue application. For a hosted
installation, configure DATABASE_URL, SECRET_KEY, STORAGE_BACKEND=r2, the same R2
values, and COOKIE_SECURE=true privately. `render.yaml` defines the web and worker
services. Run a web process with gunicorn and a separate worker with `flask --app
backend:create_app worker`. The worker supports uploads and bulk processing. The free web runner can process catalog batches; temporary exam expiry also runs on access and bounded cleanup runs on new sessions. Use a writable UPLOAD_DIR for
its regenerable cache; do not expose that directory as a public static directory.
`compose.yaml` is the existing local PostgreSQL/Redis development setup, not a
Supabase deployment recipe. Hosting has not been deployed by this update.

Latest paper percentages and bookmarks are stored only in browser localStorage. Each reattempt replaces the previous score for that paper. Clearing site data removes these records; they do not sync between devices. Detailed result/review and wrong-answer practice remain temporary (one hour); abandoned practice sessions expire after one day.
Bulk processing stays paused. Existing Excel import and future PDF uploads remain.

After deployment, bounded catalog ingestion is explicit: `python bulk_ingest.py
--limit 20`; use `--retry-failed --limit 10` for failed papers and `--dry-run` to
inspect the next batch without changing the database.

## Direct student access and admin login

Students open a paper and start Practice or Exam without registering or signing in.
Admin login: `/#/admin/login`; admin panel: `/#/admin`. Existing admin email/password
credentials remain valid. All administrative APIs still require an active admin session.

Exam sessions are owned by a random signed browser-session cookie, with only its
hash stored on temporary attempts. No guest user rows, permanent server progress,
or server bookmarks are created. Timer, scoring, answer-key privacy and CSRF checks
remain server enforced. At most five active sessions per browser are allowed.

The normal startup migration adds nullable guest ownership to temporary attempts;
it preserves existing accounts and content. Old account scores are not copied into
browser storage. Returning visitors start with browser-local progress.

### Responsive interface and content reports

The original layout and theme styles remain in `frontend/src/style.css`.
`frontend/src/features.css` adds only compact available-paper cards and styles
for reporting and loading feedback. Available papers show their term, source
filename, question/marks counts and a test link in a compact responsive grid.

Next to Bookmark, **Report Broken Format** opens an optional-detail form for text,
formula, image, options or other issues. Reports require no student login. The
server accepts only available, non-archived questions and stores one report per
browser/question, with CSRF protection, a 20-new-reports/hour browser cap and a
60-requests/hour IP cap. No email, name or raw session cookie is collected.
Admins use **Content Reports** to filter Open/Resolved reports, inspect the
question and mark a reviewed issue resolved or reopen it. Resolution changes
only the report status; corrections still go through the existing content workflow.
Reports are included in dependency-ordered library reset. The startup migration
creates the report table without rewriting existing papers or questions.

Starting practice/exam shows an immediate indeterminate progress indicator and
skeleton while the request runs; start buttons are disabled until success/failure.
Loading feedback also covers restored attempts and mode switching. It indicates
activity rather than claiming a percentage or reducing the network duration.

### Admin content recovery and corrections

- **Processing → failed paper → Upload replacement PDF** targets that existing
  paper with its metadata retained. After upload, **Process now** processes one
  queued file in this request (no paid worker needed); Refresh also follows a job
  claimed by the normal worker. The paper must not already have queued/active jobs.
  For canonical aliases, replace the original canonical paper instead.
- **View failed questions** selects the paper and Extraction failed filter. Full
  processing warnings remain in the job details, including rejected record numbers.
- **Question bank → Edit question**, or **Content Reports → Edit question**, opens
  text/passage, option, answer-key, marks, explanation and image correction controls
  with a live preview and original source PDF/page. Choice keys use JSON, e.g.
  `["A","B"]`; NAT uses a number; `null` means an unavailable answer key.
- Save correction or Save & resolve report records the before/after state in the
  existing QuestionReview audit table. Undo latest change is itself audited. Image
  assets/rows are retained so old snapshots and undo continue working; uncheck an
  old image and save to remove it from new attempts after adding a replacement.
- Hide/Restore is available in the bank and editor; use the Hidden filter to find
  hidden questions. Counts/marks for new attempts include only available questions.
- Manual edits/hides are locked in question evidence. Extraction matches exact
  fingerprints or one unambiguous current question number, preserves locked rows,
  and flags unmatched admin overrides for review rather than overwriting them.
  If a replacement produces no valid questions, existing available content is
  retained. Ambiguous/renumbered sources require admin review of preserved overrides.
- Version checks prevent stale saves and queued/active ingestion blocks concurrent
  edits. Admin authentication and CSRF protection apply to every content mutation.
  Existing temporary attempts keep their snapshots. No schema migration is needed.

The exam scientific calculator runs locally, without an external iframe. It
supports degree/radian trig and inverse/hyperbolic functions, powers, roots, logs,
factorial, modulus, percentages and memory. Expressions are parsed as arithmetic
without JavaScript evaluation. Functions use parentheses; `logbase(base,value)`
and `root(degree,value)` accept two arguments. Use multiplication explicitly.

### Source bold and request feedback
New PDF imports preserve bold text from native PDF font flags/names in question stems,
shared passages and options. Parsing still uses plain text for boundaries, keys and marks.
Emphasis is applied only to an unambiguous source slice; uncertain mappings stay plain.
OCR pages do not contribute bold ranges. Existing papers are not automatically repaired.
`**bold text**` is also supported in the admin editor preview and student content. Rendering
uses text nodes and `<strong>` only, never raw HTML, and leaves math/image markers intact.

Loaders reflect actual library, start-session, admin save/upload/process/retry, report and
submit requests. Failures retain visible errors and restore controls. Reduced-motion
preferences disable spinner animation. Exam options and navigation have no new animation.

## AI solutions: local PC generation

Admin → AI Solutions queues small batches; a single local Windows worker generates Gemini text solutions, and administrators review/edit/publish them. Published explanations load only after practice Check answer or exam submission. Start Exam does not invoke AI or include solution text. Setup instructions: [tools/ai-worker/README.md](tools/ai-worker/README.md). Normal deployment migrations add the queue/solution tables; no source answer keys or scoring rules are changed.

## Admin analytics

The administrator's Analytics tab reports paper starts, completions, completion
rate, average elapsed completion time, course/paper totals and basic device type.
Content Reports also includes **Hide & mark resolved** beside Mark resolved.
It hides the reported question and resolves that report in one transaction,
records an audit entry, and preserves existing attempt snapshots. The action
checks the question version and rejects edits during active paper processing.

Today and Last 7 days use IST calendar dates (including today); timestamps remain
UTC epoch values. Completions belong to the attempt's **start date**, original
mode and original device group. Timer-triggered submissions are included and
shown separately. Elapsed time includes idle time, so it does not by itself
measure difficulty. Bookmark/topic/wrong-answer collections are excluded.

Run `flask --app backend:create_app db upgrade` before starting the updated app.
Existing attempts without analytics snapshots are not backfilled. Collection
starts after deployment; no historical counts are invented.

The existing Start/Submit requests enqueue small anonymous snapshots after their
main transaction commits. A lazy per-process daemon writes batches of up to 100
events once per second, using its own single-connection pool and short timeouts.
There are no additional learner requests, analytics polling, GA4, IP storage,
raw User-Agent storage, fingerprints, answers or visitor identifiers in analytics.
Device classification is a coarse mobile/desktop/unknown hint, not identification.

The queue holds 1,000 events per process. Overflow and failed batches are dropped;
analytics failures do not fail Start/Submit. A crash/restart can lose queued
events. The admin details show **this process's** queue/drop/failure counters;
they reset on restart and are not global durable health totals. Under multiple
web workers, requests may display different local counters.

Daily summaries are permanent and independent of expiring learner sessions or
deleted catalog papers. Dashboard queries use summaries rather than raw event
history and show the top 50 papers/courses. Deduplication receipts are retained
for 30 days and pruned in bounded batches on writes. The command
`flask --app backend:create_app cleanup-analytics` also prunes up to 100 old receipts during
quiet periods; repeat as needed. Events older than 30 days are ignored so old
replays cannot recreate totals after receipt removal. A completion arriving
before its start event still records one real start and one completion.

Set `ANALYTICS_ENABLED=false` in the environment to disable collection.
`ANALYTICS_QUEUE_SIZE` controls the bound. Tests default to manual flushing;
production starts the writer lazily after fork. Summary storage can later be
rolled into monthly summaries without changing the learner request flow.
