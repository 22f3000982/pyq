# Usage analytics validation

- Backend: 33 tests passed (analytics, content reports, engine, guest access).
- Frontend: 3 tests passed (admin analytics loading/no polling and hide-and-resolve).
- Production frontend build and git diff whitespace check passed.
- Isolated SQLite migrations: upgrade to previously deployed 0009, then upgrade to
  durable ledger 0010 passed. No production database was modified by these tests.
- Local SQLite alternating ON/OFF benchmark: 35 measured samples per condition
  after warmup. Off/on median Start 2.96/3.45 ms; p95 3.48/3.86 ms. Submit median
  2.64/3.45 ms; p95 3.07/3.94 ms. These numbers are local smoke measurements,
  not cloud/network/concurrent load performance or a Render latency guarantee.

The ledger is durable after successful commits, independent of temporary attempts.
Analytics failures intentionally leave incomplete counts rather than failing main
learner actions. No event queue silently drops records on normal process restart.
Monthly archival summary tables remain a future optimization. Admin aggregation
uses indexed minimal records and a 30-second bounded cache; heavy all-time reports
still share database resources with learner requests.
