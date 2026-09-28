# PYQ Studio final code release — 27 September 2026

## Implemented and tested locally

- NAT/short-text responses update immediately while typing, autosave, survive timer
  ticks/polling/refresh, and flush before navigation, submission and mode switching.
- One permanent PaperProgress row per user/paper; server-scored retakes update it.
- Cards display `You already attempted this QP and scored 80.0%.` (latest percentage).
- Existing result/review/wrong-answer practice remain available for one hour after
  submission. Detailed responses are temporary, not permanent history.
- Active untimed practice expires after seven days. Timed sessions use the server
  deadline. The background worker removes expired session records. Keep it running.
- Full-paper practice/exam submissions update progress; targeted practice does not.
- Stable courses, terms, exam types, papers, source entries, questions, options,
  images and ingestion metadata are preserved by the guarded migration path.
- Development users, attempts, attempt answers, bookmarks, reviews and latest
  progress are disposable and are excluded from the stable migration snapshot.
- Flask/SQLAlchemy reads DATABASE_URL with SQLite fallback locally and psycopg
  PostgreSQL in Render; Render refuses an implicit SQLite production fallback.
- R2 supports separate PDF/image buckets, immutable checksum-verified objects and
  a regenerable local cache. Bulk catalog acquisition remains bounded and paused.

## Verification status

See FINAL-BACKEND-TESTS.txt, FINAL-FRONTEND-TESTS.txt and FINAL-FIVE-PAPER-TESTS.json.
Frontend utility tests: 3 passed; production Vite build passed.
Real-paper API flows passed for all five available demo papers (111 questions).
The acceptance tests roll back their writes; every application table's content
was checked before and after the run. Tests used an isolated SQLite copy.
Browser visual testing and live Render deployment are not claimed.

The current read-only external audit verified Supabase DNS, PostgreSQL connectivity,
schema inventory and stable-content digests against SQLite. R2 DNS/HTTPS reaches the
configured endpoint, but the current private credential pair returns
`SignatureDoesNotMatch`; no R2 objects were changed.

## Automatic migration after private configuration

Stop the new app/worker before running MIGRATE.cmd. The command:

1. Backs up the prepared local SQLite database using a read-only source connection,
   checks integrity/references and records a hash. Never edits that source database.
2. Requires PostgreSQL DATABASE_URL, runs read-only SELECT 1 and rolls back.
3. Applies the schema, then reconciles stable records: identical rows are skipped,
   missing rows are inserted, destination-only rows are preserved, and conflicts
   stop the run without silent overwrites.
4. Checks Python and Node/npm test prerequisites.
5. Applies existing Alembic migrations to a working COPY, removing only disposable
   development session/progress rows in that copy; the original SQLite is untouched.
6. Applies those same migrations to Supabase; enables RLS on backend tables so the
   frontend cannot fetch private tables directly through Supabase's Data API.
7. Imports stable application tables with existing IDs and relationships in one data
   transaction; verifies rows and preserves destination-only data.
8. Runs backend tests in isolated temporary schemas on that PostgreSQL database,
   plus frontend tests/build. SQLite-specific migration tests remain SQLite tests.
9. Tests the five real imported papers against the migrated tables inside a rollback
   transaction: practice, exam, palette, images, responses, scoring, review, retake,
   progress uniqueness and timeout. No verification users/results are retained.
10. Checks all source stable rows again and compares logical stable contents rather
    than using disposable activity or SQLite physical layout as a gate.
    Only then writes migration-ready.json. START.cmd now uses that verified target.

On any failure the runner stops, writes a sanitized stage/error report and leaves
activation disabled. The original installation/SQLite/PDFs remain available.
Schema creation may already have succeeded if a later step fails. The tool does
not destroy those tables or silently retry over them; inspect the report first.
Backups/reports are under migration-backups/<timestamp> in the NEW installation.
Backups contain private data: keep them private and outside Git.

If using a different destination URL later, it must pass migration/testing again;
the startup marker checks target identity. Do not manually edit that marker.
Use START.cmd for guarded startup, not the old direct run_local.py shortcut.

## Rollback

Stop the new application and worker. Start the ORIGINAL unchanged project using
its existing Python and scripts/run_local.py. Its users, database and PDFs remain
as they were before preparation. Activity performed only on the new installation
or Supabase is not automatically copied back. Do not run both copies at once.
