# Changelog — epubveri library for calibre

## [0.4.0] — 2026-09-12

- **A scan is kept, so the report survives calibre closing.** *Show the last
  report* used to mean "this session"; now the last two scans of each library
  are on disk and it means the last one, whenever that was. Nothing is read at
  startup — the file is opened when you ask for the report, so a plugin you
  have installed and are not using costs nothing.

  Kept even when a scan finds nothing, which is the case worth stating: a
  library that came back clean is exactly the baseline a later comparison
  wants, and a scan is only cheap to repeat until it is ten minutes long.

  **Filed under calibre's own id for the library**, which is the one guard
  here that is structural rather than checked: a report names books by id, an
  id means a different book in another library, and a stored report simply is
  not there to load against the wrong books.

  Nothing else is guarded, on purpose. Books get added, repaired and deleted
  after a scan — the report is a dated observation and it carries its date,
  its book count and its epubveri version so you can judge the drift. Silently
  dropping ids that no longer resolve would make it a worse observation, not a
  safer one.

- **Two scans can be compared.** *Compare with the previous scan* subtracts
  them: one row per rule, books before, books after, and the change — `RSC-005
  … 181 → 12`. Rules that did not move are hidden until asked for, and the
  ordering is by **how far a row moved in either direction**, because a row on
  400 books that did not budge is the least interesting line in a comparison
  and a regression is the most.

  This is the question no single report can answer, and the one this family of
  tools is shaped around: epubveri finds, epubsana repairs, *did that help*.

  **When the two scans were run by different versions of epubveri, the window
  says so.** A rule we added, changed or stopped reporting looks exactly like
  a book that was repaired, and nothing here can tell those apart. Refusing to
  compare across versions would be worse — most comparisons a user makes will
  span a release, because our releases are more frequent than their scans.

- **The entry in the plugin list is one line.** It ran to three where
  calibre's own run to one — *"Copy a book from one calibre library to
  another"* — so in a column of short rows ours was the tall one, which reads
  as a plugin that needs explaining. It no longer restates the plugin's own
  name either, which the row above it already carries.

  What it gives up is the cross-reference to the editor plugin, which was put
  there because calibre's plugin *type* files the two under different headings
  and cannot say they belong together. That argument was real and it lost to a
  worse cost: the reference sat three lines into a paragraph nobody finishes.
  It is in the README, in the forum thread, and now on the settings page
  beside the validator, where somebody is already reading.

- **A selection scan is shown but not kept as a baseline.** Checking five
  selected books is a useful thing to do and a ruinous thing to measure three
  thousand against: every rule those five books do not happen to contain would
  read as a rule that had been repaired. Only a whole-library scan becomes the
  thing a later comparison subtracts from, and both sides of a comparison come
  off disk for the same reason.

- **The settings page is short instead of tall** (owner). It had grown a
  section per release — what the report ranks, how many books at once, the
  validator, the saved reports — and four framed group boxes down a column
  made it taller than the dialog that opens it: 432 px of content in a window
  that shows less.

  It is four bold headings, a dimmed line under each, and seven one-line
  controls. **The page is short because its text is short**: each long
  explanation is the control's tooltip, which is where something you read once
  belongs rather than permanently occupying the page.

  The dimmed lines are a correction to the first attempt at that, which had
  the headings and nothing else and was *too* bare — a column of words with no
  hint what ranking a usage note would do to you. One line a section is the
  middle term, and it costs about 14 px where a paragraph cost 60.

  **A tabbed version shipped in between and was withdrawn.** It fixed the
  height and brought something worse: on the owner's machine, clicking one
  particular tab dropped calibre's modal Customize dialog behind the
  Preferences window, where the first two tabs were covered, clicks landed on
  a window the modal had blocked, and only Escape got out. It was never
  reproduced here — the real dialog, real mouse events, with and without a
  parent window — and the dialog, its modality and its placement all belong to
  calibre. What goes inside it is ours, so the tab widget went. The class
  docstring says so where someone would go to add it back.

  Three things measured while rendering it, each a real defect:

    * **calibre wraps this page in a `QScrollArea`**, so an over-wide page is a
      horizontal scrollbar rather than a wider window. Ours was 704 px against
      a 682 px viewport, because word-wrapped paragraphs and checkbox labels —
      which do not wrap at all — demand width. Now 388.
    * The spin box showed `utomatic (8)`: a `QSpinBox` sizes itself to its
      number range, not to its special value text, and the range is 0-8. Its
      minimum width is measured off its own font now, rather than padded by a
      guess that would fit English and clip German.
    * The saved-report size printed `0.0 MB` directly above a button offering
      to delete it, because a real pair of saved scans is about 20 KB. The
      megabyte unit came from the 18 000-book estimate, where it is right.

- **Preferences says how much is stored and can delete it.** A saved report
  holds the titles of the books each defect was found in, which is not what
  anyone expects a validator to leave in a config folder unless told. The size
  is shown beside a button that removes it; both were measured before any of
  this was written — 474 real books produce 0.13 MB of JSON, 0.02 MB gzipped,
  so even an 18 000-book library lands under a megabyte for both slots.

- **Found by running it rather than by reading it**: the comparison table and
  the CSV that same window writes came out in different orders, because the
  table was left to sort itself and Qt chose the message id. One set of rows
  with two orders is exactly the thing nobody notices until they are holding
  both artefacts. Now pinned by a test that compares the two.

## [0.3.0] — 2026-09-12

- **The report window stays open when you click a row.** maddz reported it
  (MobileRead 375207 #14) on a 7 912-book library that takes eight minutes:
  one click on a row to see which books carry a defect, and the window — and
  the scan behind it — was gone.

  The window closed because it was *modal*, and that was not a detail. A modal
  dialog is the only thing you can touch while it is up, so filtering the
  library view behind one would have shown nobody anything; closing was the
  only way to hand the books over. It is modeless now, so a row is a question
  the report can be asked over and over, and the next row after that.

  Two consequences worth stating. A second scan closes the report the first one
  left, rather than leaving two windows claiming to describe the same library.
  And switching libraries closes it — the report names books by id, an id means
  a different book in another library, and marking those would be worse than
  showing nothing.

- **Three menu entries that existed only as code.** *Show the last report*
  brings a closed window back without re-reading a book; *Show books with no
  EPUB* finds the ones a scan counted but could not look at; *Clear the marks
  it left* removes this plugin's own marks and nobody else's.

  All three were written for 0.1.0, with the reasoning, and **none of them was
  ever connected to the menu** — the commit that added them describes the menu
  it did not change. So the answer to maddz's report had been sitting in the
  source for five days with no way to ask for it. `Clear the marks` had a
  second defect underneath the first: it called a method that was never
  written, which nothing noticed because nothing could reach it. Both halves
  are fixed and both are now tested.

  Each entry is greyed out when there is nothing for it to do, and each can be
  given a keyboard shortcut under Preferences → Advanced → Shortcuts.

- **Export writes a per-book CSV as well as the report.** DNSB asked for one
  (375207 #13): one row per book and defect — book id, title, message, rule,
  severity, and **how many times that book trips it**.

  That last column is why this is not a one-line change. A row of the report
  held a *set* of book ids, which can say that 181 books carry a defect and
  cannot say that one of them carries it forty times. It counts per book now.

  Both exports follow the filter the window is showing, because a checkbox that
  changes the window and not the file would make two artefacts out of one
  report.

- **A report says what it is a report of.** The window carries a second line,
  and both exports and the clipboard carry the same facts: when the scan ran,
  how long it took and how many books at once, which epubveri, which plugin,
  which calibre, the operating system and the core count. *What this scan was*
  in the Copy menu puts them on the clipboard as plain text.

  Two reasons, and the first is the one that makes a stored report honest. **A
  report is a dated observation, not a statement about the library today**
  (owner): books get added, repaired and removed, and the date and book count
  beside the findings are what let a reader judge how far it has drifted.
  Comparing two reports needs the epubveri version for the same reason — the
  difference between them can be the books or it can be our release notes, and
  without the version there is no way to tell which.

  The second is a use the owner named: a user who posts "1 000 books in 48
  seconds" is telling other people something they can act on only if the
  cores, the worker count and the version are beside the number.

  The operating system is named the way its own users name it — `macOS 26.6.2`
  rather than Python's `macOS-26.6.2-arm64-arm-64bit-Mach-O`, which is
  accurate and is not a thing anyone would type into a forum post.

- **Neither half of the toolbar button starts a scan, and it keeps its
  arrow.** A plain click used to repeat whichever scope was used last, which
  the README has said it does not do since 0.1.0 — the line that would have
  made that true was never committed, so for five days a stray click could
  start a ten-minute scan whose scope nothing on the button named.

  The obvious fix cost something real: it dropped the drop-down arrow, and
  every other menu-bearing button in calibre has one, so ours stopped looking
  like part of the application. The arrow is back, and the body of the button
  — which that mode would otherwise wire to the action — opens the same menu
  the arrow does. Both halves do one thing and neither can start ten minutes
  of work by accident.

- **Preferences said the validator was shared with the editor plugin. It is
  not**, and has never been: the two keep separate copies on purpose, because a
  library scan holds the binary open for ten minutes and Windows will not let a
  running executable be overwritten. The sentence told a user that installing
  either plugin was enough for both.

## [0.2.0] — 2026-09-10

- **The scan validates several books at once, and you choose how many.**
  DNSB scanned about 18 000 books in 1 h 29 min on an idle system
  (MobileRead 375207 #2, #8) and the whole of that was one book at a time.

  How much faster depends entirely on your machine, so this note does not
  give you a number to compare yours against. Not every core is worth the
  same — a laptop with a mix of fast and efficient cores gains noticeably less
  than its core count suggests — and the scan is limited by the processor
  rather than by the disk, so a slow drive is not what holds it back.

  The other reason is that we cannot see your machine. A **Books validated at
  the same time** control is in Preferences → Plugins → Customize, and its
  maximum is your physical core count less two: two are kept for the rest of
  the system, calibre included. Physical rather than logical cores, because on
  a hyperthreaded 8-core machine the logical count is 16 and reserving two of
  those would still leave fourteen processes fighting over eight cores.

  It defaults to **Automatic**, which is that maximum, or the number of books
  if the selection is smaller — a fourth worker on three books has nothing to
  do.

  An estimate that also read free memory and the size of the largest books was
  written and then removed: measuring it showed a scan costs far less memory
  than it was insuring against, and the library it would have protected — one
  of large illustrated books, bulk-scanned on a small laptop — is one nobody
  has reported. If yours behaves that way, say so and it can be built against
  a real library rather than a guess about one.

- **It is listed as the GUI plugin it is.** Its category was forced to "Edit
  book tool" so that it would sit beside the editor plugin in Preferences →
  Plugins — one product, one heading — with the known cost that the heading
  named where its *sibling* lives rather than where it does.

  MobileRead settled that the other way: a moderator retitled the thread
  **[GUI Plugin] epubveri library**, and it is filed under *Extend calibre
  generally*. That is calibre's own community answering the same question, so
  a Preferences entry reading "Edit book tool" would now disagree with the
  index a user found the plugin in. It takes its own category, and the two
  plugins name each other in their descriptions instead — which the category
  never could do anyway.

  Nothing functional turns on it: all three uses in calibre are cosmetic.

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
