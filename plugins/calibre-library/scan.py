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


#: Peak resident memory one epubveri process needs, as a function of the book.
#: Measured across the reference shelf: an 80.7 MB book peaked at 90.4 MB, a
#: 0.9 MB book at 8.4 MB — so a fixed baseline plus about the size of the file.
#:
#: The floor is the second dimension. Size is not the only thing that costs:
#: a 0.7 MB book carrying 6 859 findings peaked at 17-32 MB, because the
#: findings themselves are held. A library of small files is therefore not as
#: cheap as its sizes suggest, and the floor is what stops the estimate saying
#: it is.
_WORKER_BASELINE_BYTES = 10 * 1024 * 1024
_WORKER_SIZE_FACTOR = 1.2
_WORKER_FLOOR_BYTES = 35 * 1024 * 1024

#: How much of what is *available* a scan may plan to use. Half, because
#: calibre is in this process too and the rest of the machine is not ours.
_RAM_BUDGET = 0.5

#: Where more workers stopped buying speed, measured on one machine: ten
#: physical cores, 120 real books, warm cache. 4 workers gave 3.3x, 6 gave
#: 4.5x, 8 gave 4.9x, 10 gave 5.0x and 12 gave 5.3x — so ten cores produced
#: 5x, not 10x, and the bottleneck is disk and decompression rather than the
#: core count.
#:
#: **This bounds the recommendation, never the setting.** It is one machine's
#: number and another's disk may keep more workers fed; a user whose scan is
#: still CPU-bound can raise the value to `worker_cap()`. What it prevents is
#: offering a 64-core workstation sixty workers for a few per cent.
_KNEE = 8


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


def recommended_workers(jobs=(), cap=None, available_bytes=None):
    """A starting value for this machine and this library.

    A fixed default is wrong in both directions, and that is why this is
    computed rather than chosen: four workers is timid on a publisher's
    workstation with 128 GB, and too many on a four-core laptop with 8 GB.
    The user still owns the final value — this only stops them starting from a
    number that was never about their machine.

    **The library is half of the answer and it is free to ask.** The memory a
    worker needs tracks the size of the book it is on, and calibre already
    knows every book's size, so the largest EPUB in the selection sizes the
    estimate instead of a guess standing in for it.

    `available` rather than `total` memory: this machine has 32 GB installed
    and 9.2 GB free as this is written, and it is the second that decides
    whether a scan pushes calibre into swap.
    """
    cap = worker_cap() if cap is None else cap
    largest = 0
    for job in jobs:
        path = job[2] if len(job) > 2 else None
        try:
            largest = max(largest, os.path.getsize(path))
        except (OSError, TypeError):
            continue
    per_worker = max(_WORKER_FLOOR_BYTES,
                     _WORKER_BASELINE_BYTES + _WORKER_SIZE_FACTOR * largest)
    if available_bytes is None:
        try:
            import psutil
            available_bytes = psutil.virtual_memory().available
        except Exception:                               # noqa: BLE001
            # No reading is not a reason to refuse to scan; it is a reason not
            # to be ambitious. One worker is what this plugin did until now.
            return 1
    by_ram = int((available_bytes * _RAM_BUDGET) // per_worker)
    return max(1, min(cap, _KNEE, by_ram))


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

    `abort` is checked before each book is handed out, so cancelling a scan of
    three thousand books stops within about one book's time and **keeps what it
    has**. That is the whole reason this returns a report rather than raising.
    With a pool the books already in flight are allowed to finish; they are
    counted, not thrown away.

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
