# OPPE admin preview

This release keeps **all** OPPE endpoints behind active ADMIN authentication and CSRF checks. There is no public release switch yet: enabling public access later requires a reviewed change. READY is a content status, not public visibility. The home card is visible only after admin login. Existing PYQ data and scoring are unchanged.

## App setup

1. Install backend dependencies and `npm ci` in frontend.
2. Run `flask --app 'backend:create_app' db upgrade` using the application's existing database configuration. This creates only `oppe_course` / `oppe_question` and seeds Python, DBMS, PDSA, Java, SC. Do not reset the database.
3. `npm run build` in frontend.
4. Sign in as admin. Home → Practice OPPE (or `/admin/oppe`).
5. Manage questions → Add question. Fill statement, topic, category, code, reference solution, explanation, sample and hidden test cases.
6. Save draft → Validate reference solution → Mark ready for admin preview.

A saved draft can be previewed before validation. Run/Submit are disabled until the runner is configured. They never execute locally in the Flask web process.

## Questions and imports

- Import template gives `mauryahub-oppe-v1` JSON. The selected-course template contains one ORIGINAL demonstration, not third-party copied content. Import it as a draft to test the complete workflow.
- Import supports 1–50 questions per course, maximum 3 MB. Use unique stable `external_id` values.
- Preview → Save imported drafts. Import is atomic; any invalid question stops the entire import. Overwrite must be selected explicitly. It resets content to DRAFT and clears validation.
- Reference solution contains the editable middle only. Server composes `prefix + submitted_code + suffix`. Include necessary line breaks in the fixed parts.
- Drafts may omit tests/reference code. Validation and final submission require ≥1 visible sample, ≥1 hidden test and reference code. Each test specifies stdin, expected stdout, and optional safe relative fixture files (`{"data.txt":"hello\n"}`).
- SQL runtime is **PostgreSQL 16**, not SQLite or MySQL. Provide `setup_sql` schema and seed data; each test can override it with its own `setup_sql` for different hidden datasets. Output uses psql unaligned tuples-only format (`|` separates columns). Use ORDER BY for deterministic ordered results. Setup errors fail validation.
- SC runtime is Bash on Debian. Each test starts from fresh fixture files. Work in the current directory; print or inspect produced file content to stdout. No internet, root permissions or host files.
- Java entry class is configurable (`entrypoint`, default `Main`, JDK 21); standard input/output. PDSA uses Python 3.12.
- Output comparison is exact after CRLF normalization and removal of final newlines; spaces, internal blank lines and ordering remain significant. Float-tolerance and unordered SQL result comparators are not supported yet.
- Editing a question invalidates prior reference validation. Revision checks reject stale saves/submissions. A successful reference run checks test consistency, not whether the explanation or test coverage is educationally correct.
- The practice endpoint excludes hidden cases, SQL setup and reference code. Hidden test execution returns only verdict and duration; no hidden input/output/errors. Reveal uses a separate authenticated endpoint.
- Course → Add course supports new names and categories using one of the four supported runtimes. New execution languages require a runner implementation.

## Separate execution host

**Do not run the gateway on the Render PYQ service or mount Docker into it.** Use a dedicated Linux Docker host, without production credentials or data. Docker containers add isolation but share the host kernel; before public release use hardened disposable workers or stronger VM isolation and review abuse/load controls.

Gateway requirements:

1. Install supported Docker Engine from its official source on the dedicated host.
2. Pre-pull the four images: `python:3.12-slim`, `eclipse-temurin:21-jdk`, `mauryahub-oppe-shell:1` (build with `docker build -t mauryahub-oppe-shell:1 tools/oppe-runner/images -f tools/oppe-runner/images/Dockerfile.shell`), `postgres:16-alpine`. For production, pin reviewed image digests and patch them regularly.
3. Install `tools/oppe-runner/requirements.txt` in its own venv.
4. Generate a random token ≥32 characters. Set `OPPE_RUNNER_TOKEN` on both the gateway and PYQ app. Never put the token in frontend code or Git.
5. From `tools/oppe-runner`, run `gunicorn --bind 127.0.0.1:8090 --workers 1 --threads 4 --timeout 650 runner:app`.
6. Put the gateway behind HTTPS and restrict ingress to the app where feasible. Configure `OPPE_RUNNER_URL=https://your-runner-host` in the PYQ service. Plain HTTP is accepted only for localhost development.
7. Run the original Python template through Validate, Run and Submit; then validate one original question per runtime. Finally test deliberate infinite loops, excessive output, filesystem access, forks and SQL errors on the dedicated test host before opening it publicly.

The gateway allows two concurrent requests per process and rejects additional work with 429. Main app limits practice execution to 12 requests/minute/IP and reference validation to 6. Each test gets a fresh non-root container with no network, read-only root/source, dropped capabilities, no-new-privileges, memory/CPU/process/file limits and bounded output capture. Python/SC get writable temporary fixture copies. Java compilation has a separate 10-second bound; runtime has the question limit. SQL uses PostgreSQL statement_timeout plus outer watchdog. Displayed elapsed time includes container overhead; it is not CPU time.

**Environment limitation:** Docker is not installed in the implementation workspace. API tests use a controlled runner stub; actual four-runtime container execution must be verified on the dedicated Docker host. No production migration, deployment, runner service creation or GitHub push has been performed.

## Known scope limits

- No third-party question bank copied. Import authorised/original source material.
- JSON import is implemented; direct ZIP/PDF-to-question ingestion is not.
- There are no student accounts, OPPE analytics or permanent OPPE attempt records in this preview. Code lives in the open component; switching questions resets it. Closing the page loses it.
- SC checks stdout; filesystem-result assertions beyond printed file content need a future checker. SQL is stdout-based, with deterministic expected output.
- Shell has basic plain-text editing, while Python/Java/SQL have syntax highlighting.


## Owner-authorized source import (20 October 2026)

The seed migration adds 278 source questions as private, unvalidated DRAFTS: Python 100, Java 80, PDSA 50, SC 48. It skips existing stable source IDs and never overwrites edited questions. DBMS has no questions in the captured source menu. Another 100 MLP statements are archived separately, not activated, because their dataset/notebook/NAT workflow is outside the requested five courses.

Visible starter code, reference solutions and samples are preserved. Hidden tests were not exposed by the source and must be authored before validation/submission. Imported reference code is not a reviewed stepwise explanation. SC file-result questions explicitly block stdout-only grading until a filesystem checker exists.

Embedded diagrams are packaged as authenticated local image assets. External diagram downloads may fail with source HTTP 503; affected drafts carry an explicit note and source image link. Restore those diagrams before considering the affected questions complete. No missing diagram is silently treated as validated content.

Python function tasks support `python-call` or allowlisted `python-dispatch`, with source argument decoding and structured result comparison. Other tasks use stdin/stdout. SC fixtures and safe environment variables are copied into isolated temporary workspaces. These protocol adaptations have unit coverage; actual sandbox execution still needs a Docker host verification.

To regenerate import bundles from the captured records, install development conversion dependencies `markdownify` and `requests`, then run `python scripts/prepare_oppe_source.py`. This script only parses/downloads content; it never executes imported code.
