# epubveri library — the scan itself, and how its findings are grouped
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Validate many books and turn the result into a report about *rules*.

**The report is rule-first, and that is the one design decision in this plugin
worth arguing.** The obvious shape is a list of books with an error count, and
it was measured and rejected over a 474-book library:

  * A *fatal / won't open* column would always be empty. epubveri deliberately
    does not escalate where epubcheck does, so no real book on that library
    produced one. The column would be honest and useless.
  * **Error count is anti-correlated with variety at the top.** The
    highest-count books trip *one* rule thousands of times — one producer
    pattern repeated per paragraph — while the most varied book trips seven
    rules with two orders of magnitude fewer findings. Sorting by count puts
    the least interesting and most easily fixed book first.
  * A boolean valid/invalid column fails the same way: about half of a real
    library is invalid and a third of those by one or two findings. "Half your
    library is invalid" teaches nobody anything.

So the question this answers is not *which books are broken*. It is **"your
library has a handful of recurring producer defects; here they are, and here
is which books each one affects."** Understand one pattern, fix hundreds of
books — and every row is something epubsana may be able to repair in bulk.

The composition that follows from it: this plugin answers *which*, the editor
plugin answers *what*. A row names its books, the library view filters to
them, and opening one in Edit Book shows the findings in place.
"""

import os
import time

from calibre_plugins.epubveri_library.client import runner
from calibre_plugins.epubveri_library.client.envelope import (
    EnvelopeError, SEVERITY_ORDER)

#: The formats a scan looks at. EPUB only for now: KEPUB is a Kobo variant
#: calibre stores under its own format name, and while epubveri reads one
#: perfectly well, a KEPUB carries Kobo's own injected markup — reporting that
#: as a defect of the user's library would be wrong in a way this plugin
#: cannot explain in a table cell.
FORMATS = ('EPUB',)

#: Severities that count as a defect for the ranking. `usage` and the advisory
#: family are fetched (the runner always passes `-u --advisory`) but are not
#: ranked by default, because **this table ranks defects and a usage finding is
#: not one**. It is the difference between this report and the editor panel:
#: the panel shows one book completely, this one sorts a library's problems.
#: Both are settings; only the default differs.
DEFAULT_SEVERITIES = ('fatal', 'error', 'warning')


class RuleGroup:
    """One row of the report: a single defect, across the whole library."""

    __slots__ = ('key', 'code', 'rule', 'violation_kind', 'name', 'severity',
                 'example', 'varies', 'findings', 'book_ids')

    def __init__(self, key, finding):
        self.key = key
        self.code = finding.code
        self.rule = finding.rule
        self.violation_kind = finding.violation_kind
        self.name = (finding.params or [None])[0] if finding.violation_kind else None
        self.severity = finding.severity
        #: The first message seen — epubveri's own wording rather than a
        #: summary invented here.
        self.example = finding.message
        #: **Whether the group's messages actually agree**, which is not a
        #: detail. A grouped-by-rule row can hold messages that differ, because
        #: several rules put a value *out of the book* in their text: seven
        #: books sharing `ncx.ids.invalid_ncname` produce seven different
        #: sentences, and showing the first of them verbatim makes a row about
        #: seven books read as a row about one book's identifier. Found by
        #: running this over real books, where it was the top row.
        self.varies = False
        self.findings = 0
        self.book_ids = set()

    def add(self, finding, book_id):
        self.findings += 1
        self.book_ids.add(book_id)
        if not self.varies and finding.message != self.example:
            self.varies = True
        # Keep the worst severity seen. A single id can arrive at two levels
        # (a rule gated differently per EPUB version), and a row must not
        # claim to be milder than its worst member.
        if SEVERITY_ORDER.get(finding.severity, 9) < SEVERITY_ORDER.get(self.severity, 9):
            self.severity = finding.severity

    @property
    def books(self):
        return len(self.book_ids)

    @property
    def label(self):
        """What to put in the *what it says* column.

        `e.g.` when the group's messages differ, and nothing when they agree.
        Three words of hedging is the whole fix, and it is worth it: without it
        the most widespread row on a real library claims to be about one
        book's identifier.
        """
        return ('e.g. ' + self.example) if self.varies else self.example

    @property
    def is_advisory(self):
        return self.code.startswith('ADV-') or self.code.startswith('NEXT-')

    @property
    def sort_key(self):
        """Books first, then findings. **Not severity.**

        A warning on two hundred books is a producer defect worth a morning; a
        fatal on one is a single broken file, and the book list is right there.
        Severity is a column, not the ordering.
        """
        return (-self.books, -self.findings,
                SEVERITY_ORDER.get(self.severity, 9), self.code)


def group_key(finding):
    """How two findings are decided to be the same defect.

    `(violation_kind, params[0])` is a **documented** group key: epubveri
    promises the token's spelling per kind, precisely so a consumer can group
    without parsing English. So when a finding carries a kind, the construct it
    names joins the key and `element "img" not allowed` becomes one row however
    many books and paragraphs it spans.

    When it does not, the key stops at the rule — because `params[0]` is then
    whatever that rule puts first, and for several of them that is a **value
    out of the book**. `ncx.ids.invalid_ncname` carries the offending id, which
    is unique per book: keyed on it, one defect across a library would become
    one row per book, which is the report this file exists to avoid.
    """
    if finding.violation_kind:
        name = (finding.params or [None])[0]
        return (finding.code, finding.rule, finding.violation_kind, name)
    return (finding.code, finding.rule, None, None)


class BookResult:
    """What one book contributed, kept so a row can name its books."""

    __slots__ = ('book_id', 'title', 'path', 'status', 'counts', 'error')

    def __init__(self, book_id, title, path):
        self.book_id = book_id
        self.title = title
        self.path = path
        self.status = 'ok'
        self.counts = {}
        self.error = None


class ScanReport:
    """Everything one scan produced. Built by `scan_books`, read by the dialog."""

    def __init__(self):
        self.groups = {}
        self.books = []
        self.requested = 0
        self.scanned = 0
        self.no_format = []
        self.unreadable = []
        self.elapsed = 0.0
        self.tool_version = ''
        self.cancelled = False
        self.note = None

    def add(self, finding, book_id):
        key = group_key(finding)
        group = self.groups.get(key)
        if group is None:
            group = self.groups[key] = RuleGroup(key, finding)
        group.add(finding, book_id)

    def rows(self, severities=DEFAULT_SEVERITIES):
        """The report, ordered. `severities` is a display filter and nothing
        more — every finding was fetched, so switching it re-sorts rather than
        re-validating a library."""
        wanted = set(severities)
        rows = [g for g in self.groups.values() if g.severity in wanted]
        rows.sort(key=lambda g: g.sort_key)
        return rows

    def affected_ids(self, severities=DEFAULT_SEVERITIES):
        ids = set()
        for group in self.rows(severities):
            ids |= group.book_ids
        return ids

    def hidden_counts(self, severities=DEFAULT_SEVERITIES):
        """`{severity: findings}` for what the current filter is leaving out.

        Shown rather than dropped: a user who does not know `usage` exists
        should still be told the number, which is how the editor plugin's
        equivalent line came about.
        """
        wanted = set(severities)
        out = {}
        for group in self.groups.values():
            if group.severity not in wanted:
                out[group.severity] = out.get(group.severity, 0) + group.findings
        return out


#: How many individual failures the log names before it stops naming them.
#: A library where every book fails would otherwise put one line per book back
#: into the log by the other door — and the failures are all in the report
#: anyway, which is where a reader can page through them.
MAX_LOGGED_FAILURES = 50


def _log_failure(trace, logged, result):
    """Name a book that could not be read, up to `MAX_LOGGED_FAILURES`.

    A failure is worth a line even though the report already holds it: if the
    scan later dies, the report is never rendered and the log is all there is.
    """
    if logged < MAX_LOGGED_FAILURES:
        trace('could not read: %s - %s' % (result.title, result.error))
    elif logged == MAX_LOGGED_FAILURES:
        trace('further unreadable books are in the report, not the log')
    return logged + 1


def scan_books(binary, jobs, report=None, abort=None, notify=None,
               timeout=runner.DEFAULT_TIMEOUT, log=None):
    """Validate `jobs`, a list of `(book_id, title, epub_path)`.

    **One process per book, deliberately.** Batching several `-i` inputs into
    one invocation is supported by epubveri and would amortise process startup,
    but startup was measured at under a millisecond per book on the reference
    library — 385 books took 68.85 s in one process against 69.17 s in one
    process each. What per-book buys instead is worth far more here: a cancel
    that takes effect within one book, progress that is a real fraction, and a
    pathological archive that costs its own timeout rather than a whole batch's.

    `abort` is checked between books, so cancelling a scan of three thousand
    books stops in about a fifth of a second and **keeps what it has**. That is
    the whole reason this returns a report rather than raising.
    """
    report = report if report is not None else ScanReport()
    report.requested = len(jobs)
    started = time.time()
    # **A trace, sized by the library rather than by the book count.** DNSB
    # scanned 18 000 books in an hour and a half (MobileRead 375207 #2, #8) and
    # the log said two things: that it started, and — if it reached the end —
    # that it finished. Nothing in between, so a run that died at book 12 000
    # would have left no evidence of where. One line per book is the obvious
    # fix and the wrong one: 18 000 lines to read, written on the job thread,
    # inside the loop we are timing. A constant ~40 lines answers "where did
    # it stop and how fast was it going" at any library size, and costs
    # nothing measurable.
    step = max(1, len(jobs) // 40)
    failures_logged = 0

    def trace(message):
        if log is not None:
            log(message)

    for index, (book_id, title, path) in enumerate(jobs):
        if abort is not None and abort.is_set():
            report.cancelled = True
            trace('cancelled after %d of %d' % (index, len(jobs)))
            break
        if notify is not None:
            notify(float(index) / max(1, len(jobs)), title)
        if index and index % step == 0:
            spent = time.time() - started
            trace('%d/%d, %.0f s, %.3f s/book' % (index, len(jobs), spent,
                                                  spent / index))

        result = BookResult(book_id, title, path)
        try:
            envelope = runner.run_epubveri(binary, path, timeout=timeout)
        except EnvelopeError as exc:
            result.status = 'failed'
            result.error = str(exc)
            report.unreadable.append(result)
            report.books.append(result)
            failures_logged = _log_failure(trace, failures_logged, result)
            continue
        except Exception as exc:                        # noqa: BLE001
            # A timeout, a killed process, a file that vanished between the
            # database query and the run. None of these is a reason to lose
            # the other 2 999 books.
            result.status = 'failed'
            result.error = '%s: %s' % (type(exc).__name__, exc)
            report.unreadable.append(result)
            report.books.append(result)
            failures_logged = _log_failure(trace, failures_logged, result)
            continue

        if not report.tool_version:
            report.tool_version = envelope.tool_version
        result.counts = dict(envelope.summary)
        if envelope.could_not_read:
            result.status = 'failed'
            result.error = envelope.error or 'epubveri could not read this file'
            report.unreadable.append(result)
            failures_logged = _log_failure(trace, failures_logged, result)
        for finding in envelope.findings:
            report.add(finding, book_id)
        report.books.append(result)
        report.scanned += 1

    report.elapsed = time.time() - started
    return report


def collect_jobs(db, book_ids, report):
    """`(book_id, title, path)` for every book that actually has an EPUB.

    A library holds books in other formats and books whose file is missing;
    both are recorded rather than skipped silently, because "you scanned 2 700
    of 3 000" is information and a quiet 2 700 is a wrong denominator.
    """
    jobs = []
    for book_id in book_ids:
        path = None
        for fmt in FORMATS:
            try:
                path = db.format_abspath(book_id, fmt, index_is_id=True)
            except Exception:                           # noqa: BLE001
                path = None
            if path:
                break
        try:
            title = db.title(book_id, index_is_id=True)
        except Exception:                               # noqa: BLE001
            title = '(unknown)'
        if not path or not os.path.exists(path):
            result = BookResult(book_id, title, path)
            result.status = 'no format'
            report.no_format.append(result)
            continue
        jobs.append((book_id, title, path))
    return jobs
