# Changelog — epubveri library for calibre

## [0.2.0] — 2026-09-10

- **The scan validates several books at once, and you choose how many.**
  DNSB scanned about 18 000 books in 1 h 29 min on an idle system
  (MobileRead 375207 #2, #8) and the whole of that was one book at a time.

  Measured over 120 real books on ten physical cores: 1 worker 14.38 s,
  4 workers 4.30 s (3.3x), 8 workers 2.94 s (4.9x). It saturates around six to
  eight, and **ten cores gave five times the speed rather than ten** — the
  limit is the disk and the decompression, not the processor. So a library on
  a network share or an external drive may well do better with fewer workers,
  which is one of the two reasons this is a setting rather than a number we
  picked.

  The other reason is that we cannot see your machine. A **Books validated at
  the same time** control is in Preferences → Plugins → Customize, and its
  maximum is your physical core count less two: two are kept for the rest of
  the system, calibre included. Physical rather than logical cores, because on
  a hyperthreaded 8-core machine the logical count is 16 and reserving two of
  those would still leave fourteen processes fighting over eight cores.

  It defaults to **Automatic**, which is computed rather than chosen — a fixed
  default is wrong in both directions, timid on a publisher's workstation with
  128 GB and too many on a four-core laptop with 8 GB. Automatic reads the
  cores, the *free* memory rather than the installed memory, and the largest
  book in the library, since a worker costs roughly the size of the book it is
  working on. It is bounded where the measurements stopped showing a gain, so
  a 64-core machine is not offered sixty workers for a few per cent; raise the
  setting yourself if your disk keeps up.

- **What deliberately did not change.** Cancelling still stops the scan
  handing out new books and keeps everything already done — the books in
  flight are allowed to finish and are counted rather than discarded. One
  pathological archive still costs only its own timeout. And the report is
  identical whatever the worker count: the book list is filled by each book's
  own position rather than in the order results happen to arrive, and the rule
  rows were already safe because their sort key ends in the rule's own code.
  Both are asserted by tests that were checked by breaking the guarantee and
  watching them fail.

## [0.1.1] — 2026-09-09

- **A long scan leaves a trace in the job log now**, which was promised in
  MobileRead 375207 #4 after DNSB scanned an 18 000-book library. The log said
  two things before: that the scan started, and — only if it reached the end —
  that it finished. A run that died at book 12 000 left no evidence of where,
  which is exactly the case the log existed for.

  There is a progress line every 2.5% of the way through, carrying the
  position, the elapsed time and the seconds per book, so **the log is about
  forty lines whether the library holds a hundred books or twenty thousand**.
  One line per book would have been the obvious fix and the wrong one: 18 000
  lines to read, written on the job thread, inside the loop being timed. The
  cost of the version that shipped is not measurable — 120 books took 14.32 s
  with it and 14.34 s without.

  Each book that could not be read is named as it happens, up to fifty of
  them; after that the log says so and leaves the rest to the report. A
  failure that is only in the report is invisible if the scan never gets far
  enough to render one. A cancelled scan now says where it stopped, and the
  first lines name the validator binary the run is using.

- **The closing line gives the rate.** DNSB reasonably asked whether an hour
  and a half for 18 000 books was normal; a run can now answer that about
  itself instead of being compared with someone else's machine.

  For what it is worth, measured here rather than guessed: over 120 real books
  this plugin's own overhead — everything that is not epubveri — is **2 ms per
  book, 1.6% of the total**. Nearly all of a scan is the validator, so the
  number your library reports is a fact about your machine and your books.

- **The README's example report is a sketch now, not one library's numbers.**
  It printed the real counts from the library this was designed against, which
  read as a claim about EPUBs in general. They are not — every library's rows
  and numbers are its own. The columns were the point, so the columns stayed
  and the numbers became placeholders. (The measurement itself is still in
  `scan.py`, where it belongs: it is the record of why the report is shaped
  this way, not a statistic offered to a reader about their own books.)

## [0.1.0] — 2026-09-07

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
- **Its own copy of the validator**, in `plugins/epubveri-library-data/`,
  independent of the editor plugin's. Sharing one was tried first and dropped:
  a scan holds the binary open for ten minutes, Windows does not allow a
  running executable to be overwritten, and the other plugin's hourly update
  check would land in the middle of that. The install record sits beside the
  binary, so deleting the folder leaves nothing behind that describes a file
  that is gone.
