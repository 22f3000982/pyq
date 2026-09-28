# Verification of the consolidated update

- Exact runtime: Node 22.10.0.
- npm ci --engine-strict: passed after pinning all incompatible direct/transitive dependencies.
- Frontend: 18 component tests, 3 utility tests, production build passed.
- Backend regression suite and additional SDK contract test: see included logs.
- R2 tests cover immutable upload/deduplication, checksum validation, cache recovery,
  path traversal rejection, sanitized failures, authentication on image routes,
  real PDF ingestion and boto3 request parameter validation with Stubber.
- Five real-paper practice/exam/scoring/review/retake/timeout flows passed against
  a copy of the uploaded SQLite database and a stubbed S3 object store with an
  initially EMPTY local cache. All 324 original assets were verified in that test.
- Source database remained unchanged; acceptance writes were rolled back and all
  application table digests checked. Source PDFs were retained.
- Safe resume requires exact source/target/content match; modified remote contents
  stop the operation without overwriting anything.
- Missing R2 configuration remains PENDING, not a false completed state.

Live external checks completed separately from these isolated local tests:

- Supabase DNS, PostgreSQL connection, schema inventory, and read-only catalog
  counts succeeded. Stable catalog/content/ingestion digests match the current
  SQLite source; no migration writes were performed by that check.
- R2 DNS and HTTPS reach the configured endpoint, but the current private access
  key/secret pair returns `SignatureDoesNotMatch`. No R2 objects were changed.

The Windows setup command retains the live migration and storage readback gates.
Deployment and a live-browser production smoke test remain pending until the R2
credential pair is corrected.
