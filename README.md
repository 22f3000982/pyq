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

Existing logins, courses, questions, PDFs and latest progress remain in use.
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
backend:create_app worker`. The worker is required
for uploads, deadline processing and expiry cleanup. Use a writable UPLOAD_DIR for
its regenerable cache; do not expose that directory as a public static directory.
`compose.yaml` is the existing local PostgreSQL/Redis development setup, not a
Supabase deployment recipe. Hosting has not been deployed by this update.

Only latest user/paper progress is permanent. Detailed result/review and wrong-answer
practice remain temporary (one hour); active practice expires after seven days.
Bulk processing stays paused. Existing Excel import and future PDF uploads remain.

After deployment, bounded catalog ingestion is explicit: `python bulk_ingest.py
--limit 20`; use `--retry-failed --limit 10` for failed papers and `--dry-run` to
inspect the next batch without changing the database.
