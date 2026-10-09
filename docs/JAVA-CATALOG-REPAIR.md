# Java / App Dev-1 May and September 2025 repair

The supplied diploma workbook has swapped course names on these term rows. Its
row codes and PDF filename prefixes agree: CS2005 is Java; CS2003 is App Dev-1.
The old importer preferred the row name, assigning the sources to the wrong course.

## After deployment

1. Admin → Papers → **Repair Java / App Dev-1 May/Sep 2025**.
2. The action previews the affected existing records and asks for confirmation.
3. Known wrong Java sources are corrected and queued in a processing batch.
4. Use Processing to fetch/process this batch using the existing Drive connection.
5. Confirm the resulting Java PDFs/questions, then continue the normal next batch.

No new Excel or PDF upload is needed for this bounded repair. Java Quiz 1, Quiz 2
and End Term mappings in these two terms are covered. App Dev-1 source metadata
is corrected for future batches, but its already corrected question bank is not
reprocessed. Different custom source URLs, archived papers, and other terms are
untouched. A repeated click queues no duplicate jobs. Active jobs block repair.
The previous bank remains until extraction validates; existing attempt snapshots
are retained. The repair itself does not generate or transfer old solution text.

## Future imports

When a recognized PDF filename code and the row code agree, their corroborating
code wins over a contradictory row name. With no corroboration, existing name
matching remains in place and the conflict is reported. Source URLs cannot match
an existing paper from a different course/term/exam/session during reconciliation.
Identical files can share storage, but question-bank aliases never cross courses.

An optional CLI `repair-catalog-sources PATH --course-code CS2005 --term "May 2025"
--term "Sep 2025"` previews corrections from a supplied workbook. `--apply` queues
those corrections. The bounded admin repair above is preferred for this incident.
