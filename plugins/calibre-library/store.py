# epubveri library — keeping a scan after the window closes
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Two scans per library on disk: the last one, and the one before it.

**Two, not a history, and the reason is that a third answers nothing a second
does not.** The two questions people actually have are *"show me that report
again"* — maddz's eight-minute library, MobileRead 375207 #14 — and *"is my
library better than it was"*. The first needs the last scan; the second needs
exactly two. A list of ten would be ten times the disk for the same two
answers, and every entry past the second would be a report whose library has
moved on further.

**Keyed by `library_id`, which is the one guard that has to be structural.** A
report names books by calibre id, and an id means a different book in another
library. Filing each library's scans under its own uuid means a stored report
cannot be shown against the wrong books — not because something checks, but
because it is not there to load.

**Nothing else is guarded, deliberately** (owner, 2026-09-12). Books get added,
repaired and deleted after a scan; the report is a *dated observation*, not a
claim about the library today, and it carries its date, its book count and its
epubveri version so a reader can judge the drift themselves. Quietly dropping
ids that no longer resolve would make it a worse observation, not a safer one.

**Size was measured before this was written**, because "store the whole report"
deserves a number rather than a shrug: 474 real books produced 162 rules and
54 283 findings, which serialise to 0.13 MB of JSON and 0.02 MB gzipped — 282
and 49 bytes a book. DNSB's 17 703-book library therefore lands near 5 MB raw
and under 1 MB compressed, for both slots together. Gzip is used anyway: the
cost is a fraction of a second at the end of a ten-minute job, and it is the
difference between a plugin that leaves megabytes in a config directory and one
that does not.
"""

import gzip
import json
import os

from calibre_plugins.epubveri_library import PLUGIN_VERSION
from calibre_plugins.epubveri_library.install import data_dir
from calibre_plugins.epubveri_library.scan import BookResult, RuleGroup, ScanReport

#: The shape of what is written. Bumped when a stored file can no longer be
#: read by this code — a reader that does not recognise the number treats the
#: file as absent rather than guessing, which is why loading can never raise.
FORMAT = 1

CURRENT = 'current'
PREVIOUS = 'previous'


def reports_dir(create=True):
    """Where the saved scans live.

    `create=False` exists because **the menu asks whether a report is there
    every time it opens**, and a question should not build a folder: before
    anyone has ever run a scan this plugin would otherwise leave a directory
    tree in the config folder just for having been installed. `data_dir` takes
    the same flag for the same reason.
    """
    path = os.path.join(data_dir(create=create), 'reports')
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def _path(library_id, slot, create=True):
    # `library_id` is a uuid calibre generates, so it needs no escaping — but
    # it arrives from a database rather than from us, and a path built out of
    # foreign text is worth keeping to characters that cannot leave the
    # directory. Anything else is dropped rather than substituted: two
    # libraries whose ids differ only in punctuation would otherwise share a
    # file, which is the one failure this module exists to make impossible.
    safe = ''.join(c for c in str(library_id or 'unknown')
                   if c.isalnum() or c in '-_')
    return os.path.join(reports_dir(create),
                        '%s-%s.json.gz' % (safe or 'unknown', slot))


# -- turning a report into text and back ---------------------------------

def _group_to_dict(group):
    return {
        'code': group.code, 'rule': group.rule,
        'violation_kind': group.violation_kind, 'name': group.name,
        'severity': group.severity, 'example': group.example,
        'varies': group.varies, 'findings': group.findings,
        # JSON object keys are strings whatever they were; they come back as
        # ints in `_group_from_dict`, because a calibre book id is an int
        # everywhere else in this plugin and a string one would mark nothing.
        'book_counts': {str(book_id): count
                        for book_id, count in group.book_counts.items()},
    }


def _group_from_dict(data):
    group = RuleGroup.__new__(RuleGroup)
    group.key = (data.get('code'), data.get('rule'),
                 data.get('violation_kind'), data.get('name'))
    group.code = data.get('code') or ''
    group.rule = data.get('rule')
    group.violation_kind = data.get('violation_kind')
    group.name = data.get('name')
    group.severity = data.get('severity') or 'error'
    group.example = data.get('example') or ''
    group.varies = bool(data.get('varies'))
    group.findings = int(data.get('findings') or 0)
    group.book_counts = {int(book_id): int(count) for book_id, count
                         in (data.get('book_counts') or {}).items()}
    return group


def _book_to_dict(result):
    # `path` is not written. It is the largest field per book and the least
    # portable — an absolute path into a library that may since have moved —
    # and nothing reads it once a scan is over.
    return {'book_id': result.book_id, 'title': result.title,
            'status': result.status, 'counts': result.counts,
            'error': result.error}


def _book_from_dict(data):
    result = BookResult(data.get('book_id'), data.get('title') or '', None)
    result.status = data.get('status') or 'ok'
    result.counts = data.get('counts') or {}
    result.error = data.get('error')
    return result


def to_dict(report):
    return {
        'format': FORMAT,
        'plugin': PLUGIN_VERSION,
        'started_at': (report.started_at.isoformat()
                       if report.started_at is not None else None),
        'requested': report.requested,
        'scanned': report.scanned,
        'elapsed': report.elapsed,
        'tool_version': report.tool_version,
        'cancelled': report.cancelled,
        'note': report.note,
        'workers': report.workers,
        'scope': report.scope,
        'machine': [list(pair) for pair in report.machine],
        'groups': [_group_to_dict(group) for group in report.groups.values()],
        'books': [_book_to_dict(result) for result in report.books],
        'no_format': [_book_to_dict(result) for result in report.no_format],
    }


def from_dict(data):
    from datetime import datetime

    report = ScanReport()
    report.requested = int(data.get('requested') or 0)
    report.scanned = int(data.get('scanned') or 0)
    report.elapsed = float(data.get('elapsed') or 0.0)
    report.tool_version = data.get('tool_version') or ''
    report.cancelled = bool(data.get('cancelled'))
    report.note = data.get('note')
    report.workers = int(data.get('workers') or 1)
    report.scope = data.get('scope') or 'library'
    report.machine = [tuple(pair) for pair in (data.get('machine') or [])]
    stamp = data.get('started_at')
    if stamp:
        try:
            report.started_at = datetime.fromisoformat(stamp)
        except ValueError:
            report.started_at = None
    for raw in data.get('groups') or []:
        group = _group_from_dict(raw)
        report.groups[group.key] = group
    for raw in data.get('books') or []:
        result = _book_from_dict(raw)
        report.books.append(result)
        # Rebuilt rather than stored: `unreadable` held the same objects as
        # `books`, and writing both would let a file describe a book as failed
        # in one list and fine in the other.
        if result.status == 'failed':
            report.unreadable.append(result)
    for raw in data.get('no_format') or []:
        report.no_format.append(_book_from_dict(raw))
    return report


# -- disk -----------------------------------------------------------------

def save(library_id, report):
    """Write `report` as this library's current scan, demoting the last one.

    **Nothing here may take a scan down with it.** Ten minutes of work has
    already happened and the window is about to open; a full disk is a reason
    to lose the saved copy, never the report in front of the user. So this
    returns whether it wrote rather than raising, and the caller carries on
    either way.
    """
    try:
        current = _path(library_id, CURRENT)
        if os.path.exists(current):
            previous = _path(library_id, PREVIOUS)
            os.replace(current, previous)
        _write(current, to_dict(report))
        return True
    except Exception:                                   # noqa: BLE001
        return False


def _write(path, payload):
    """Written beside and renamed into place.

    A scan interrupted mid-write would otherwise leave a truncated file that
    loads as nothing — which is the same as no file, except that it has also
    thrown away the good one it replaced.
    """
    temporary = path + '.tmp'
    raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    with gzip.open(temporary, 'wb') as handle:
        handle.write(raw)
    os.replace(temporary, path)


def load(library_id, slot=CURRENT):
    """The stored scan, or None. **Never raises**, for the same reason `save`
    does not: a menu entry that explodes is worse than one that does nothing,
    and every way this can fail — no file, half a file, a format from a later
    version — has the same honest answer."""
    try:
        path = _path(library_id, slot, create=False)
        if not os.path.exists(path):
            return None
        with gzip.open(path, 'rb') as handle:
            data = json.loads(handle.read().decode('utf-8'))
        if int(data.get('format') or 0) != FORMAT:
            return None
        return from_dict(data)
    except Exception:                                   # noqa: BLE001
        return None


def exists(library_id, slot=CURRENT):
    """Is there something to load? Asked by the menu, which runs every time it
    opens and must not read megabytes to grey out an entry."""
    try:
        return os.path.exists(_path(library_id, slot, create=False))
    except Exception:                                   # noqa: BLE001
        return False


def stored_size():
    """`(files, bytes)` across every library. Read by the settings page.

    **A saved report holds the titles of the books it found something in**,
    which is not what a user expects a validator to leave in a config folder
    unless told. Saying how much is there, and offering to remove it, is the
    least that owes them — and it is why this is in Preferences rather than in
    the menu, where it would read as part of the workflow instead of as
    something the plugin is doing on their behalf.
    """
    files = total = 0
    try:
        directory = reports_dir(create=False)
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                files += 1
                total += os.path.getsize(path)
    except Exception:                                   # noqa: BLE001
        pass
    return files, total


def forget_all():
    """Every stored report, for every library. Returns how many files went."""
    removed = 0
    try:
        directory = reports_dir(create=False)
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    removed += 1
            except Exception:                           # noqa: BLE001
                pass
    except Exception:                                   # noqa: BLE001
        pass
    return removed
