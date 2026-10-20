# Validation — admin OPPE preview

Base repository commit: `771dad82a904a94766b8945a0da280b65d00efda` (22f3000982/pyq).

- Focused backend: 14 passed. Covers anonymous access/CSRF, initial courses, atomic imports, overwrite, forbidden fixture paths, reference validation gating, stale edits, hidden-output filtering, all five original course templates, runner HTTP errors, fixed code composition and Docker gateway isolation flags.
- OPPE component: 3 passed. Covers disconnected runner state, code/revision submission, hidden-result display, explicit reset and authoring form.
- Existing Node tests: 16 passed.
- Production frontend build: passed; OPPE/CodeMirror are a separate lazy chunk.
- Isolated SQLite full Alembic upgrade → OPPE-only downgrade → re-upgrade: passed, five courses seeded.
- Broad backend suite at integration checkpoint: 261 passed, one existing date-dependent analytics failure (`test_ist_ranges_no_fabricated_history_expiry_and_new_browser`). The assertion expects an October 10 record to be in the future, which is no longer true on the current test date.
- Broad Vue suite at integration checkpoint: 97 passed, one existing progress test failure. It expects the former “Review solutions” button; the existing result page now uses question palette review.
- Both failures were independently reproduced in a clean detached worktree of the base commit. Their production modules were not edited for OPPE.

Not verified: real Docker execution (Docker is absent here), live PostgreSQL migration/RLS execution, deployed UI/mobile browser rendering and production load. No production data changed, no remote execution service provisioned and no push/deploy performed. Keep the feature private until runner execution is verified on the dedicated host.


Owner import follow-up:
- All 278 normalized source records pass the backend content validator.
- Full isolated SQLite upgrade seeds 278 private drafts; seed downgrade/re-upgrade preserves them without duplicates.
- OPPE renderer/component: 4 tests passed, including table/image rendering and unsafe HTML/image/link rejection.
- Runner tests cover Python call/dispatch harness generation, structured result comparison, environment forwarding and custom Java class naming. Docker execution remains unverified.
- 11 unique embedded diagrams were packaged locally. 15 questions depend on external images whose source requests returned errors; their drafts retain a source link and explicit restoration warning. One SC file-output question requires a filesystem checker and blocks stdout-only grading.
