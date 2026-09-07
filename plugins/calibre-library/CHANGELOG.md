# Changelog — epubveri library check for calibre

## [0.1.0] — unreleased

First version. Validates a calibre library with epubveri and reports the
defects that recur across it.

- **A rule-first report.** One row per defect, ordered by how many books carry
  it, rather than a list of books with error counts. The three measurements
  behind that choice are in the README; the short version is that a
  book-and-count report ranks the least interesting book first.
- **Whole library or selection**, as a background job with progress in the Jobs
  panel. Cancelling keeps what the scan already found.
- **Show affected books** marks the books a row names and filters the library
  view to them, so the way out of the report is into calibre's own view — and
  from there into Edit Book, where the editor plugin says what is wrong in
  place.
- **Export or copy** the report as CSV, carrying the grouping fields
  (`violation_kind`, the construct named) as well as the counts.
- Errors and fatals are always ranked; warnings by default. Usage notes and
  advisory findings are fetched but not ranked unless asked for, and the window
  says how many findings the filter is hiding.
- **The validator binary is shared with the editor plugin.** One download
  serves both, and the record of which binary it is lives beside the binary —
  a per-plugin record goes stale the moment the other plugin updates it, and
  the editor plugin refuses to run a binary whose hash it does not recognise.
