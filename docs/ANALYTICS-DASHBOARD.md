# Admin learning analytics dashboard

## Scope
Admin → Analytics. Processing stays at 20; no Process 50 control was added.
Admin paper attempts count identically to student paper attempts from this update.
The dashboard is lazy-loaded and available only through the existing admin authorization.

## Metrics and actions
- Period/custom dates, searchable course and initial mode filters; scoped CSV export.
- Daily starts/submissions, weekly distinct active browsers, returning browser estimates,
  exam/practice mix, device mix, IST activity heatmap and course/paper demand.
- Completion, active/incomplete attempts, assisted submissions and average duration.
- Recorded unassisted exam scores and distribution. Old missing scores remain unavailable.
- Current published solution coverage, popular papers missing solutions, open reports,
  low-scoring papers and low-accuracy questions, with links to the relevant admin action.
- Accuracy warnings require at least 20 graded unassisted exam responses. Low-score paper
  warnings require at least 20 recorded exam scores. These are review signals, not proof
  of a content error. Edited question versions are excluded from old accuracy totals.

Browser counts are estimates from a first-party pseudonymous cookie, not verified people
or all homepage visitors. Returning means activity on more than one recorded IST day or
before the selected range. Clearing cookies/changing devices affects counts. Durations
include idle time. Incomplete attempts do not establish why a student left.

## Performance and privacy
No additional per-question tracking request, polling loop, analytics SDK or chart package.
Reports load only on opening/filtering/refresh, cached 30 seconds; content coverage caches
for 120 seconds. Dashboard charts are not loaded by ordinary quiz users.

Production PostgreSQL completion tracking combines the existing event upsert and daily
question totals into one SQL statement/round trip. SQLite development uses one additional
bulk write, never one write per question. An isolated savepoint contains analytics errors.
These writes still use database resources; zero latency overhead is not guaranteed.
Question totals contain counts and content versions, not selected answers, typed responses,
IP addresses, names or browser identifiers. Event browser identifiers are not exposed in
reports or CSV. No historical admin activity or missing score is fabricated.

## Migration and rollout
Run the normal existing Flask-Migrate upgrade before serving the new backend:
`flask --app backend:create_app db upgrade` (with the deployment's normal environment).
Revision: `6e1d86bd1109`, parent `d10a00ee0013`.
The migration adds nullable event score/exam fields and an aggregate daily question table.
On PostgreSQL, RLS and client-role grant restrictions protect both analytics tables.
Use the backend's privileged database connection, not anonymous frontend table access.
No production database was modified during implementation.

## Validation
- Focused backend analytics/performance coverage: 33 tests passed; latest analytics-only
  rerun: 13 passed after the final label refinement.
- Focused frontend admin/solution coverage: 13 passed; latest dashboard rerun: 4 passed.
- Production frontend build passed.
- SQLite migration upgrade/downgrade/re-upgrade passed with existing records retained.
- PostgreSQL SQL-engine check using PGlite passed for 40-question bulk aggregation,
  duplicate submissions, additive counters and atomic savepoint rollback.
- Broader backend run: 285 passed, one existing bounded-query test failed (6 vs 5).
  Broader frontend run: 105 passed, one existing progress button expectation failed.
  Both failures reproduce on unchanged commit 34acd2d.
- Live Supabase load testing and browser visual inspection were not performed. The cloud
  browser could not connect to the local development server. Responsive/dark layouts have
  component coverage and a successful build, not a claimed live screenshot review.

A local SQLite test-client microbenchmark (40 questions, 5 warmups, 30 measured flows)
measured baseline/current median start 5.15/6.00 ms and submit 6.09/11.68 ms. This is a
small local synthetic check, not a controlled production benchmark or a capacity claim.
PostgreSQL uses the combined statement rather than SQLite's extra bulk statement.
