# Use this release in your existing PYQ project

This is application source, built frontend and tests. It intentionally contains no `.env`, database, uploaded PDFs, private keys, or test-user database. Keep your existing private configuration and source uploads.

1. Extract the ZIP. Copy the contents of its `pyq` folder into your **existing Git checkout of 22f3000982/pyq**. Replace matching code files. Do not delete the existing project folder, `.env`, `uploads`, or databases.
2. Open a terminal in that Git checkout and inspect `git status`. Commit/push using your own configured GitHub login. Do not add `.env`, uploaded data or databases; the supplied `.gitignore` excludes them. The archive includes built frontend files. Render's Docker build also rebuilds the frontend.
3. Render web and worker need the same existing Supabase/R2 configuration. Required: `APP_ENV=production`, PostgreSQL `DATABASE_URL`, `SECRET_KEY`, `STORAGE_BACKEND=r2`, `R2_ENDPOINT_URL`, the matching R2 S3 access/secret keys, `R2_PDF_BUCKET_NAME=pyq-pdfs`, `R2_IMAGE_BUCKET_NAME=pyq-images`, the correct existing `R2_PREFIX`, `COOKIE_SECURE=true`, and writable `UPLOAD_DIR=/data/uploads`. Do not make buckets public. The worker service must be running for automatic uploads to finish.
4. **Existing production database: do not run MIGRATE.cmd or FINISH-SETUP.cmd as a deployment step.** There is no new database migration in this release. Do not reset/import the catalog again. `START.cmd` is the old local launcher and is not the production entry point. Render uses the Docker Gunicorn command.

## The currently configured R2 buckets are empty

Code deployment alone cannot restore absent formulas/images. On the computer with the existing extracted PDFs/images, set the current PostgreSQL and private R2 settings in `.env`, then use the project's existing Python environment. From the project root:

```bat
python -m flask --app backend:create_app check-db
python scripts/sync_r2.py --source-dir "C:\Users\ashis\Downloads\PYQ-Studio-Final-App\uploads" --dry-run
```

Use the actual existing uploads directory if it is elsewhere. The dry run reads the current PostgreSQL asset references and both R2 buckets. If it reports missing local files or a connection error, stop and correct that specific path/connectivity issue. Do not change credentials in chat.

Once that preflight succeeds, the same command without `--dry-run` uploads missing assets, checks immutable content fingerprints and verifies downloaded checksums. It never writes to PostgreSQL, deletes originals, reparses papers, changes credentials, or overwrites conflicting R2 objects:

```bat
python scripts/sync_r2.py --source-dir "C:\Users\ashis\Downloads\PYQ-Studio-Final-App\uploads"
```

Production remains Supabase + private R2. Local files under `/data/uploads` are an expendable asset cache/processing workspace; original content resides in R2.

## After deployment

Hard-refresh the browser. Sign in using your existing account. Verify admin upload catalog options, then open each five-paper landing page, start Practice/Exam, view formulas/diagrams, answer NAT and MCQ questions, navigate, submit and review. Retake should update the same paper progress record.

For bounded future ingestion, run in the production-configured environment:

```bat
python bulk_ingest.py --limit 20 --dry-run
python bulk_ingest.py --limit 20
python bulk_ingest.py --retry-failed --limit 10
```

Tests for developers:

```bat
python -m pytest
cd frontend
npm ci
npx vitest run
npm test
npm run build
```

Detailed evidence and remaining verification limits: `docs/PRODUCTION-STABILIZATION.md`.
