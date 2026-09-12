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
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime

from calibre_plugins.epubveri_library import PLUGIN_VERSION
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
                 'example', 'varies', 'findings', 'book_counts')

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
        #: `{book_id: findings in that book}` rather than a set of ids. The
        #: set was all the table needed — a row is ranked by how many books
        #: carry it, not by how often — but the per-book export cannot be
        #: derived from it: "this book trips this rule" and "this book trips
        #: it forty times" are the difference between a list and a report, and
        #: DNSB asked for the second (MobileRead 375207 #13). Counting costs
        #: the same dictionary the set already was.
        self.book_counts = {}

    def add(self, finding, book_id):
        self.findings += 1
        self.book_counts[book_id] = self.book_counts.get(book_id, 0) + 1
        if not self.varies and finding.message != self.example:
            self.varies = True
        # Keep the worst severity seen. A single id can arrive at two levels
        # (a rule gated differently per EPUB version), and a row must not
        # claim to be milder than its worst member.
        if SEVERITY_ORDER.get(finding.severity, 9) < SEVERITY_ORDER.get(self.severity, 9):
            self.severity = finding.severity

    @property
    def book_ids(self):
        """The books this row names, as a set.

        A fresh set per call, which is why the callers that union several rows
        together do so rather than mutating what a group holds. Kept as a
        property instead of a field so that the counts cannot disagree with
        the ids the way two stored collections can.
        """
        return set(self.book_counts)

    @property
    def books(self):
        return len(self.book_counts)

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


def describe_machine():
    """The facts a scan was carried out under, as `(label, value)` pairs.

    **A report is a dated observation, not a statement about the library
    today** (owner, 2026-09-12), and that is what makes these load-bearing
    rather than decoration. Two reports of the same library can differ because
    the books changed *or* because the validator did; without the version
    beside each one there is no way to tell, and a user comparing them would
    credit their own repairs with our release notes. The date and the book
    count are what tell a reader how far a stored report has drifted from the
    library it describes — the owner's answer to staleness, and a better one
    than any check we could run for them.

    The machine half is here for a use the owner named: a user posting "1 000
    books in N seconds on M cores" only says something another user can act on
    if the cores, the worker count and the version are beside the number.

    Nothing here may raise. It is read on a worker thread during a ten-minute
    job, and no fact in it is worth failing a scan for.
    """
    import platform
    import sys
    pairs = []

    def add(label, value):
        if value:
            pairs.append((label, str(value)))

    # **Named the way its own users name it**, not the way `platform.platform()`
    # spells it. That call returns `macOS-26.6.2-arm64-arm-64bit-Mach-O`, which
    # is accurate and is not something anyone would type into a forum post —
    # and this line exists to be pasted into one. `platform.release()` is no
    # good on macOS either: it gives the Darwin kernel version (25.6.0), which
    # matches no number Apple has ever shown a user.
    try:
        if sys.platform == 'darwin':
            add('system', 'macOS %s' % platform.mac_ver()[0])
        elif os.name == 'nt':
            release, build = platform.win32_ver()[:2]
            add('system', ('Windows %s (%s)' % (release, build)).strip())
        else:
            add('system', ('%s %s' % (platform.system(),
                                      platform.release())).strip())
        add('processor', platform.machine())
    except Exception:                                   # noqa: BLE001
        pass
    try:
        import psutil
        physical = psutil.cpu_count(logical=False)
    except Exception:                                   # noqa: BLE001
        physical = None
    logical = os.cpu_count()
    if physical and logical and physical != logical:
        add('cores', '%d physical, %d logical' % (physical, logical))
    else:
        add('cores', physical or logical)
    try:
        from calibre.constants import __version__ as calibre_version
        add('calibre', calibre_version)
    except Exception:                                   # noqa: BLE001
        pass
    return pairs


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
        #: When the scan started, as a local `datetime`. Local rather than UTC
        #: because the only reader is the person who ran it, and "yesterday
        #: evening" is what they are trying to remember.
        self.started_at = None
        #: How many books were validated at once. Part of the scan's
        #: conditions, not of its findings — a rate means nothing without it.
        self.workers = 1
        #: `(label, value)` from `describe_machine()`, filled by the worker.
        self.machine = []
        #: `'library'` or `'selection'`. **Only a whole-library scan is kept
        #: as a baseline**: a spot check of five books is a perfectly good
        #: report and a ruinous thing to compare three thousand against, since
        #: every rule the selection does not happen to contain reads as a rule
        #: that was repaired.
        self.scope = 'library'

    def conditions(self):
        """Everything about *this* scan rather than about the library.

        One function, so the window, the clipboard and both CSVs cannot
        describe the same run differently.
        """
        pairs = []
        if self.started_at is not None:
            pairs.append(('scanned', self.started_at.strftime('%Y-%m-%d %H:%M')))
        pairs.append(('books', '%d of %d%s'
                      % (self.scanned, self.requested,
                         ', cancelled' if self.cancelled else '')))
        if self.elapsed:
            rate = self.elapsed / self.scanned if self.scanned else 0.0
            pairs.append(('took', '%.0f s (%.3f s/book)' % (self.elapsed, rate)))
        pairs.append(('at once', str(self.workers)))
        if self.tool_version:
            pairs.append(('epubveri', self.tool_version))
        pairs.append(('plugin', PLUGIN_VERSION))
        pairs.extend(self.machine)
        return pairs

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


#: **There was a memory term here and it was removed deliberately — do not
#: put it back without a user who needs it.**
#:
#: It estimated the RAM a worker would want from the largest books in the
#: library and lowered the recommendation to fit free memory. It worked, and
#: it was measured: eight workers over the forty largest books of a 474-book
#: library peak at **331 MB** all told. That is the point. On this shelf the
#: term only began to bind below **512 MB of free memory**, which is a machine
#: already in trouble for other reasons.
#:
#: The population it protected was a library of large illustrated books —
#: comics, fixed layout — being bulk-scanned on a small laptop, and nobody has
#: reported one. The owner's call, and the family's own rule: no value is
#: invented for an unnamed need. If someone turns up whose scan swaps, they
#: will say so and the fix can be built against their library instead of
#: against a guess about it.
#:
#: The sharper reason, kept because it generalises: **a heuristic that never
#: runs is a heuristic that never gets corrected.** This one was already wrong
#: once within a day of being written — it assumed every worker would be on
#: the largest book, and predicted 854 MB where 331 was spent — and it was
#: only caught because someone thought to measure it. Left in, firing for
#: nobody, its next error would have waited for the one user it finally met.


def worker_cap():
    """The most workers the setting may be set to: physical cores less two.

    **Two are reserved for the system** (the owner's rule): a scan that makes
    the machine unusable for its duration is a bad trade for finishing sooner,
    and calibre's own UI thread is one of the things competing.

    **Physical rather than logical cores.** `os.cpu_count()` counts
    hyperthreads: on an 8-core Intel it says 16, and the rule would then offer
    14 workers — far past where any of this stops paying, at 14 times the
    memory. calibre bundles psutil, which can tell the two apart.

    The floor of 1 is not decoration: on a two-core machine `cores - 2` is
    zero, and a scan with no workers does nothing at all.
    """
    cores = None
    try:
        import psutil
        cores = psutil.cpu_count(logical=False)
    except Exception:                                   # noqa: BLE001
        cores = None
    if not cores:
        cores = os.cpu_count() or 1
    return max(1, cores - 2)


def recommended_workers(jobs=(), cap=None):
    """The worker count to start from: the cap, or the number of books.

    Deliberately not clever. The maximum this machine allows is the whole
    answer, minus the one case where it would be silly — a selection of three
    books has nothing for a fourth worker to do, and offering one would show a
    number the scan could not use.

    See the note above for the memory estimate that used to be here and why it
    is not.
    """
    cap = worker_cap() if cap is None else cap
    count = 0
    for _job in jobs:
        count += 1
    if count:
        cap = min(cap, count)
    return max(1, cap)


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
               timeout=runner.DEFAULT_TIMEOUT, log=None, workers=1):
    """Validate `jobs`, a list of `(book_id, title, epub_path)`.

    **One process per book, deliberately.** Batching several `-i` inputs into
    one invocation is supported by epubveri and would amortise process startup,
    but startup was measured at under a millisecond per book on the reference
    library — 385 books took 68.85 s in one process against 69.17 s in one
    process each. What per-book buys instead is worth far more here: a cancel
    that takes effect within one book, progress that is a real fraction, and a
    pathological archive that costs its own timeout rather than a whole batch's.

    **`workers` runs several of those processes at once, and none of the three
    reasons above is spent by it.** That argument was against *batching*, which
    is a different thing: a pool still cancels between books, still reports a
    real fraction, and still lets one bad archive cost only its own timeout.
    Measured on ten physical cores over 120 real books — 1 worker 14.38 s,
    4 workers 4.30 s, 8 workers 2.94 s.

    `abort` is checked before each book is handed out, so cancelling stops new
    books starting at once and **keeps what it has** — the whole reason this
    returns a report rather than raising.

    **What it does not do is stop immediately, and with a pool that is longer
    than it used to be.** The books already running are allowed to finish and
    are counted, so the wait after pressing cancel is the *slowest of the
    workers in flight*, not one average book. Measured on a real 104-book
    library at 8 workers: cancel pressed at 1.5 s, returned at 4.2 s, 17 books
    kept. The alternative is killing those processes and throwing away work
    the user has already paid for, which is the trade this function exists to
    refuse.

    **Order is preserved deliberately.** A pool finishes out of order, so
    `report.books` is filled by the job's own index and never appended to as
    results arrive — otherwise the same library would produce a differently
    ordered table on every scan. The rule groups need no such care: their sort
    key ends in the rule's own code, so it is total and insertion order cannot
    reach it.

    **Only this thread touches `report`.** The pool runs epubveri and hands
    back an envelope; every mutation of the report happens here, in one thread,
    which is why none of the grouping needs a lock.
    """
    report = report if report is not None else ScanReport()
    report.requested = len(jobs)
    started = time.time()
    workers = max(1, int(workers or 1))
    # Read here rather than by the caller, so that what the report says about
    # a run is what the run did — a worker count decided elsewhere and a
    # worker count used could otherwise drift apart.
    report.started_at = datetime.now()
    report.workers = workers
    report.machine = describe_machine()
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

    if workers > 1:
        trace('%d workers' % workers)

    # Filled by index, never appended to — see the docstring.
    slots = [None] * len(jobs)
    completed = 0
    handed_out = 0
    cancelled = False

    def collect(index, outcome):
        """Fold one finished book into the report. This thread only."""
        nonlocal failures_logged
        book_id, title, path = jobs[index]
        result = BookResult(book_id, title, path)
        slots[index] = result
        envelope, error = outcome
        if error is not None:
            result.status = 'failed'
            result.error = error
            failures_logged = _log_failure(trace, failures_logged, result)
            return
        if not report.tool_version:
            report.tool_version = envelope.tool_version
        result.counts = dict(envelope.summary)
        if envelope.could_not_read:
            result.status = 'failed'
            result.error = envelope.error or 'epubveri could not read this file'
            failures_logged = _log_failure(trace, failures_logged, result)
        for finding in envelope.findings:
            report.add(finding, book_id)
        report.scanned += 1

    def validate(path):
        """The only thing that runs off this thread."""
        try:
            return runner.run_epubveri(binary, path, timeout=timeout), None
        except EnvelopeError as exc:
            return None, str(exc)
        except Exception as exc:                        # noqa: BLE001
            # A timeout, a killed process, a file that vanished between the
            # database query and the run. None of these is a reason to lose
            # the other 2 999 books.
            return None, '%s: %s' % (type(exc).__name__, exc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}
        while True:
            # Hand out work up to the width of the pool. `abort` is checked
            # here rather than on completion so that cancelling stops new
            # books starting immediately, whatever is already running.
            while len(pending) < workers and handed_out < len(jobs):
                if abort is not None and abort.is_set():
                    cancelled = True
                    break
                index = handed_out
                handed_out += 1
                if notify is not None:
                    notify(float(completed) / max(1, len(jobs)), jobs[index][1])
                if completed and completed % step == 0:
                    spent = time.time() - started
                    trace('%d/%d, %.0f s, %.3f s/book'
                          % (completed, len(jobs), spent, spent / completed))
                pending[pool.submit(validate, jobs[index][2])] = index
            if not pending:
                break
            done, _ = wait(list(pending), return_when=FIRST_COMPLETED)
            for future in done:
                collect(pending.pop(future), future.result())
                completed += 1
            if cancelled and not pending:
                break

    if cancelled:
        report.cancelled = True
        trace('cancelled after %d of %d' % (completed, len(jobs)))

    for result in slots:
        if result is None:
            continue
        report.books.append(result)
        if result.status == 'failed':
            report.unreadable.append(result)

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
