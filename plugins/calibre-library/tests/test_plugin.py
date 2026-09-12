# epubveri library — tests
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Run these inside calibre's own interpreter, which is where the plugin runs:

    /Applications/calibre.app/Contents/MacOS/calibre-debug \\
        plugins/calibre-library/tests/test_plugin.py

The import shim below points `calibre_plugins.epubveri_library` at the working
tree, so the tests read the source you are editing and never an installed copy.

**What these tests can and cannot see.** They can hold the grouping decision,
the ordering, the filter and the shared install record — all of which are this
plugin's own reasoning and none of which calibre can break. They cannot see the
toolbar, the Jobs panel, or what happens when a scan of three thousand books
meets a library being written to at the same time. Every defect the sibling
plugins have had was found by a person clicking; the habit is to add a test
each time that happens, not to believe the suite.
"""

import json
import os
import sys
import tempfile
import time
import types
import unittest
import zipfile
from datetime import datetime

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TESTS_DIR)
ROOT = os.path.dirname(os.path.dirname(PLUGIN_DIR))

_pkg = sys.modules.setdefault('calibre_plugins',
                              types.ModuleType('calibre_plugins'))
if not hasattr(_pkg, '__path__'):
    _pkg.__path__ = []
_sub = types.ModuleType('calibre_plugins.epubveri_library')
_sub.__path__ = [PLUGIN_DIR]
_sub.__file__ = os.path.join(PLUGIN_DIR, '__init__.py')
sys.modules['calibre_plugins.epubveri_library'] = _sub
# Run the real `__init__.py` into it: an empty stand-in has no PLUGIN_VERSION,
# which other modules import at module level. A harness that differs from
# production in what it *defines* produces failures production never has.
with open(_sub.__file__, encoding='utf-8') as _handle:
    exec(compile(_handle.read(), _sub.__file__, 'exec'), _sub.__dict__)

import calibre_plugins.epubveri_library.config as cfg      # noqa: E402
import calibre_plugins.epubveri_library.install as install  # noqa: E402
import calibre_plugins.epubveri_library.scan as scan        # noqa: E402
from calibre_plugins.epubveri_library.client.envelope import (  # noqa: E402
    Finding, parse_envelope)

# The same fixture the two editor plugins use, so a disagreement between any of
# them is about the plugin and never about the book.
OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">urn:uuid:12345678-1234-1234-1234-123456789abc</dc:identifier>
    <dc:title>T</dc:title><dc:language>en</dc:language>
    <dc:creator></dc:creator>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="Text/ch1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>"""

NAV = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" '
       'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>T</title></head><body>'
       '<nav epub:type="toc"><ol><li><a href="Text/ch1.xhtml">Ch1</a></li></ol></nav>'
       '</body></html>')
CH1 = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">'
       '<head><title>t</title></head>'
       '<body><p fake="x">x</p></body></html>')
CONTAINER = ('<?xml version="1.0"?>\n<container version="1.0" '
             'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
             '<rootfile full-path="OEBPS/content.opf" '
             'media-type="application/oebps-package+xml"/></rootfiles></container>')

FILES = {
    'META-INF/container.xml': CONTAINER,
    'OEBPS/content.opf': OPF,
    'OEBPS/nav.xhtml': NAV,
    'OEBPS/Text/ch1.xhtml': CH1,
}


def build_epub(path):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip',
                    compress_type=zipfile.ZIP_STORED)
        for name, text in FILES.items():
            zf.writestr(name, text)
    return path


def binary():
    """Any epubveri on this machine, for the tests that need to run one.

    **Deliberately looser than the plugin itself.** In production this plugin
    uses its own folder and nothing else — that separation is the point, and
    `test_the_binary_folder_is_not_the_editor_plugins` holds it. A test suite
    that insisted on the same folder would simply skip on a machine where only
    the editor plugin has ever run, which is most of them, and silently stop
    exercising the scan.
    """
    candidates = [os.environ.get('EPUBVERI_BINARY')]
    try:
        candidates.append(install.binary_path())
    except Exception:                                   # noqa: BLE001
        pass
    from calibre.constants import config_dir
    from calibre_plugins.epubveri_library.client import binary as bin_mod
    candidates.append(os.path.join(config_dir, 'plugins', 'epubveri-data',
                                   bin_mod.binary_filename()))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def make_finding(code='RSC-005', rule='opf.content_document.schema_violation',
                 severity='error', kind='element_not_allowed', params=None,
                 message='element "x" not allowed here'):
    item = {'code': code, 'rule': rule, 'severity': severity,
            'message': message, 'data': {}}
    if kind is not None:
        item['data']['violation_kind'] = kind
    if params is not None:
        item['data']['params'] = params
    return Finding(item)


class PinnedPrefs(object):
    """Pin what a test needs and put it back. **The editor plugin's suite
    already had this class, and not copying it is how this one broke.**

    `JSONConfig('plugins/epubveri_library')` is the live file in the running
    calibre's config directory — there is no test instance of it — so a suite
    that writes to it changes the settings of whoever ran the tests. It did:
    `ConfigTests` left `show_warning` false, and three dialog tests that had
    passed a minute earlier failed, because the dialog reads the same file to
    decide which boxes are ticked.

    Two things went wrong at once and only one of them was the leak. Tests
    sharing mutable global state pass or fail on their **order**, and the order
    changed the moment a test was added — so the failure arrived attached to an
    innocent commit. Same name and same shape as the editor plugin's, so a
    reader of either suite meets one convention.
    """

    #: **Every key any test writes**, which is the whole contract — a key
    #: missing from this tuple is a setting a test changes in the *running*
    #: calibre and never puts back. `workers` was missing for exactly one
    #: afternoon and one test, and it left the owner's own preference at 1;
    #: caught by looking at a screenshot of the settings page, not by
    #: anything failing. Add the key here in the same edit that writes it.
    KEYS = ('show_warning', 'show_usage', 'show_advisory', 'autoupdate',
            'workers')

    def setUp(self):
        self._saved = {key: cfg.prefs[key] for key in self.KEYS}
        for key in self.KEYS:
            cfg.prefs[key] = cfg.prefs.defaults[key]

    def tearDown(self):
        for key, value in self._saved.items():
            cfg.prefs[key] = value


_app = None


def qt_app():
    """One QApplication for the whole run, under Fusion.

    Fusion rather than calibre's own style is load-bearing, not tidy: with
    `CalibreStyle` active the process dies with SIGBUS inside
    `CalibreStyle::standardIcon`, which wants more of a running calibre than
    `Application([])` is in a test. Documented at length in the editor
    plugin's suite, and the same thing happens here.
    """
    global _app
    if _app is None:
        from calibre.gui2 import Application
        _app = Application([])
        _app.setStyle('Fusion')
    return _app


class GroupingTests(unittest.TestCase):
    """The one design decision in this plugin, held by tests."""

    def test_schema_violations_group_on_the_construct(self):
        a = make_finding(params=['img'])
        b = make_finding(params=['img'], message='element "img" not allowed')
        self.assertEqual(scan.group_key(a), scan.group_key(b))

    def test_two_constructs_are_two_rows(self):
        a = make_finding(params=['img'])
        b = make_finding(params=['table'])
        self.assertNotEqual(scan.group_key(a), scan.group_key(b))

    def test_two_kinds_of_one_construct_are_two_rows(self):
        a = make_finding(params=['img'], kind='element_not_allowed')
        b = make_finding(params=['img'], kind='missing_attribute')
        self.assertNotEqual(scan.group_key(a), scan.group_key(b))

    def test_a_value_bearing_rule_does_not_join_the_key(self):
        """The reason the key is conditional at all.

        `ncx.ids.invalid_ncname` puts the offending id — a value out of the
        book — in `params[0]`. Keyed on it, one defect across a library becomes
        one row per book, which is the report this plugin exists to avoid.
        Findings without a `violation_kind` therefore stop at the rule.
        """
        a = make_finding(rule='ncx.ids.invalid_ncname', kind=None,
                         params=['urn:uuid:aaaa'])
        b = make_finding(rule='ncx.ids.invalid_ncname', kind=None,
                         params=['urn:uuid:bbbb'])
        self.assertEqual(scan.group_key(a), scan.group_key(b))

    def test_the_key_survives_a_missing_params_list(self):
        a = make_finding(params=None)
        self.assertEqual(scan.group_key(a)[3], None)


class OrderingTests(unittest.TestCase):

    def _report(self):
        report = scan.ScanReport()
        # One warning on many books against one error on one: the ordering
        # decision in one fixture.
        for book_id in range(20):
            report.add(make_finding(severity='warning', params=['img'],
                                    code='RSC-005'), book_id)
        for _ in range(50):
            report.add(make_finding(severity='error', params=['table'],
                                    code='RSC-005'), 99)
        return report

    def test_books_outrank_findings_and_severity(self):
        rows = self._report().rows()
        self.assertEqual(rows[0].name, 'img')
        self.assertEqual(rows[0].books, 20)
        self.assertEqual(rows[1].name, 'table')
        self.assertEqual(rows[1].findings, 50)

    def test_a_row_whose_messages_differ_says_so(self):
        """Found by running the scan over real books, not by reasoning.

        Rules that put a value out of the book in their message text group
        correctly and then display one book's sentence for all of them. The
        `e.g.` is the difference between an example and a claim.
        """
        report = scan.ScanReport()
        report.add(make_finding(kind=None, rule='ncx.ids.invalid_ncname',
                                message="id 'aaa' is invalid"), 1)
        report.add(make_finding(kind=None, rule='ncx.ids.invalid_ncname',
                                message="id 'bbb' is invalid"), 2)
        row = report.rows()[0]
        self.assertTrue(row.varies)
        self.assertTrue(row.label.startswith('e.g. '))

    def test_a_row_whose_messages_agree_is_not_hedged(self):
        report = scan.ScanReport()
        report.add(make_finding(params=['img']), 1)
        report.add(make_finding(params=['img']), 2)
        row = report.rows()[0]
        self.assertFalse(row.varies)
        self.assertEqual(row.label, row.example)

    def test_a_group_keeps_the_worst_severity_it_saw(self):
        report = scan.ScanReport()
        report.add(make_finding(severity='warning', params=['img']), 1)
        report.add(make_finding(severity='error', params=['img']), 2)
        self.assertEqual(report.rows()[0].severity, 'error')

    def test_usage_is_filtered_out_by_default_and_counted(self):
        report = scan.ScanReport()
        report.add(make_finding(severity='usage', params=['img']), 1)
        report.add(make_finding(severity='error', params=['table']), 1)
        self.assertEqual(len(report.rows()), 1)
        self.assertEqual(report.hidden_counts(), {'usage': 1})
        self.assertEqual(len(report.rows(('fatal', 'error', 'usage'))), 2)

    def test_affected_ids_follows_the_filter(self):
        report = scan.ScanReport()
        report.add(make_finding(severity='usage', params=['img']), 7)
        report.add(make_finding(severity='error', params=['table']), 8)
        self.assertEqual(report.affected_ids(), {8})
        self.assertEqual(report.affected_ids(('fatal', 'error', 'usage')),
                         {7, 8})


class StubDB(object):
    """Just enough of calibre's database for `collect_jobs`."""

    def __init__(self, paths, titles=None):
        self.paths = paths
        self.titles = titles or {}

    def format_abspath(self, book_id, fmt, index_is_id=True):
        return self.paths.get(book_id)

    def title(self, book_id, index_is_id=True):
        return self.titles.get(book_id, 'Book %s' % book_id)


class CollectTests(unittest.TestCase):

    def test_books_without_an_epub_are_recorded_not_dropped(self):
        report = scan.ScanReport()
        db = StubDB({1: None, 2: '/nowhere/missing.epub'})
        jobs = scan.collect_jobs(db, [1, 2], report)
        self.assertEqual(jobs, [])
        # Both: no format at all, and a row whose file has gone. A quiet skip
        # would make the scanned count a wrong denominator.
        self.assertEqual(len(report.no_format), 2)

    def test_a_real_book_becomes_a_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = build_epub(os.path.join(tmp, 'b.epub'))
            report = scan.ScanReport()
            jobs = scan.collect_jobs(StubDB({5: path}), [5], report)
            self.assertEqual(jobs, [(5, 'Book 5', path)])
            self.assertEqual(report.no_format, [])


class ConditionsTests(unittest.TestCase):
    """What a run records about itself, read off a real `scan_books` call."""

    def test_a_scan_records_the_machine_it_ran_on(self):
        report = scan.ScanReport()
        scan.scan_books('/nonexistent/epubveri', [], report=report, workers=3)
        self.assertEqual(report.workers, 3)
        self.assertIsNotNone(report.started_at)
        labels = dict(report.machine)
        self.assertIn('system', labels)
        self.assertIn('cores', labels)
        text = dict(report.conditions())
        self.assertIn('plugin', text)

    def test_describe_machine_never_raises(self):
        """Read on a worker thread during a ten-minute job. No fact in it is
        worth failing a scan for, so the contract is that it returns."""
        self.assertTrue(scan.describe_machine())


class ScanTests(unittest.TestCase):

    def setUp(self):
        self.binary = binary()
        if not self.binary:
            self.skipTest('no epubveri binary; set EPUBVERI_BINARY')
        self.tmp = tempfile.mkdtemp()
        self.book = build_epub(os.path.join(self.tmp, 'b.epub'))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_real_book_produces_a_report(self):
        jobs = [(1, 'One', self.book), (2, 'Two', self.book)]
        report = scan.scan_books(self.binary, jobs)
        self.assertEqual(report.scanned, 2)
        self.assertTrue(report.tool_version)
        self.assertFalse(report.cancelled)
        # The fixture carries a bogus attribute, so at least one row exists and
        # it names both books — which is the whole shape of this report.
        rows = report.rows()
        self.assertTrue(rows)
        self.assertEqual(rows[0].books, 2)

    def test_a_missing_file_is_recorded_and_does_not_stop_the_scan(self):
        jobs = [(1, 'gone', os.path.join(self.tmp, 'no.epub')),
                (2, 'real', self.book)]
        report = scan.scan_books(self.binary, jobs)
        self.assertEqual(len(report.books), 2)
        # epubveri names a missing input with PKG-018 rather than failing, so
        # this arrives as a finding; either way the second book was scanned.
        self.assertTrue(report.scanned >= 1)

    def test_cancelling_keeps_what_it_already_did(self):
        """The reason `scan_books` returns rather than raising.

        Ten minutes of work must survive a change of mind, so `abort` is
        checked *between* books and the report comes back with the ones
        already done.
        """
        class AbortAfterOne(object):
            def __init__(self):
                self.calls = 0

            def is_set(self):
                self.calls += 1
                return self.calls > 1

        report = scan.scan_books(
            self.binary,
            [(i, 'b%d' % i, self.book) for i in range(5)],
            abort=AbortAfterOne())
        self.assertTrue(report.cancelled)
        self.assertEqual(report.scanned, 1)
        self.assertTrue(report.groups)

    def test_the_log_traces_a_long_scan_without_growing_with_it(self):
        """Promised in MobileRead 375207 #4, after DNSB's 18 000-book run.

        The log said only that the scan started and — if it got there — that
        it finished, so a run that died half way left no evidence of where.
        Two properties matter and they pull against each other: there must be
        progress *inside* the loop, and the log must not become as long as the
        library. A constant number of checkpoints gives both.
        """
        log = []
        jobs = [(i, 'b%d' % i, self.book) for i in range(120)]
        scan.scan_books(self.binary, jobs, log=log.append)
        progress = [line for line in log if '/120' in line]
        self.assertTrue(progress, 'no progress line: %r' % log)
        # ~40 checkpoints whatever the size, so a 18 000-book scan logs no
        # more than a 120-book one.
        self.assertLessEqual(len(progress), 45)
        self.assertIn('s/book', progress[0])

        few = []
        scan.scan_books(self.binary, jobs[:3], log=few.append)
        self.assertLessEqual(len([l for l in few if '/3' in l]), 45)

    def test_an_unreadable_book_is_named_in_the_log(self):
        """If the scan later dies the report is never rendered, so a failure
        that is only in the report is a failure nobody can see."""
        log = []
        missing = os.path.join(self.tmp, 'nope', 'gone.epub')
        scan.scan_books(self.binary, [(1, 'Gone', missing)], log=log.append)
        named = [line for line in log if 'could not read' in line]
        if named:                       # epubveri may report it as a finding
            self.assertIn('Gone', named[0])

    def test_a_cancelled_scan_says_where_it_stopped(self):
        class AbortAfterOne(object):
            def __init__(self):
                self.calls = 0

            def is_set(self):
                self.calls += 1
                return self.calls > 1

        log = []
        scan.scan_books(self.binary,
                        [(i, 'b%d' % i, self.book) for i in range(5)],
                        abort=AbortAfterOne(), log=log.append)
        self.assertTrue([l for l in log if l.startswith('cancelled after 1')],
                        log)

    def test_a_pool_keeps_the_book_order_a_serial_scan_had(self):
        """A pool finishes out of order; the table must not.

        `report.books` is filled by the job's index rather than appended to as
        results arrive. Without that the same library produces a differently
        ordered list on every scan, which reads as the plugin being unstable
        rather than as threads being threads.
        """
        jobs = [(i, 'b%d' % i, self.book) for i in range(12)]
        serial = scan.scan_books(self.binary, jobs, workers=1)
        pooled = scan.scan_books(self.binary, jobs, workers=6)
        self.assertEqual([r.book_id for r in serial.books], list(range(12)))
        self.assertEqual([r.book_id for r in pooled.books],
                         [r.book_id for r in serial.books])
        self.assertEqual(pooled.scanned, serial.scanned)

    def test_a_pool_produces_the_same_report_as_a_serial_scan(self):
        """Same groups, same order, same counts — the rule rows are what the
        dialog shows, and they must not depend on how many workers ran.

        They are safe because `RuleGroup.sort_key` ends in the rule's own
        code, so the sort is total and insertion order cannot reach it. This
        asserts that rather than trusting it.
        """
        jobs = [(i, 'b%d' % i, self.book) for i in range(10)]
        serial = scan.scan_books(self.binary, jobs, workers=1)
        pooled = scan.scan_books(self.binary, jobs, workers=5)
        every = ('fatal', 'error', 'warning', 'usage', 'info')
        self.assertEqual([(g.code, g.books, g.findings)
                          for g in pooled.rows(every)],
                         [(g.code, g.books, g.findings)
                          for g in serial.rows(every)])
        self.assertTrue(serial.groups, 'the fixture must produce findings')

    def test_cancelling_a_pool_keeps_what_finished(self):
        """Cancel still means "stop handing out books", not "throw away".

        With a pool the books already running are allowed to finish and are
        counted. What must not happen is a cancelled scan losing work it had
        already paid for.
        """
        class AbortAfterTwo(object):
            def __init__(self):
                self.calls = 0

            def is_set(self):
                self.calls += 1
                return self.calls > 2

        report = scan.scan_books(self.binary,
                                 [(i, 'b%d' % i, self.book) for i in range(20)],
                                 abort=AbortAfterTwo(), workers=4)
        self.assertTrue(report.cancelled)
        self.assertTrue(0 < report.scanned < 20, report.scanned)
        self.assertEqual(len(report.books), report.scanned)
        self.assertTrue(report.groups)

    def test_the_cap_reserves_two_cores_and_never_reaches_zero(self):
        """The owner's rule, and the floor that keeps it usable.

        `cores - 2` is 0 on a two-core machine, and a scan with no workers
        does nothing at all.
        """
        self.assertGreaterEqual(scan.worker_cap(), 1)
        self.assertEqual(scan.recommended_workers(cap=1), 1)
        self.assertEqual(max(1, 2 - 2), 1)

    def test_never_more_workers_than_books(self):
        """The fourth worker on a three-book selection has nothing to do, and
        offering one shows a number the scan cannot use."""
        jobs = [(i, 'b%d' % i, self.book) for i in range(3)]
        self.assertEqual(scan.recommended_workers(jobs, cap=8), 3)
        self.assertEqual(scan.recommended_workers([], cap=8), 8,
                         'no jobs is not zero books; it is no information')

    def test_the_cap_is_the_whole_recommendation(self):
        """No memory estimate, no invented ceiling — see the note in scan.py.

        This asserts the *absence* on purpose. A recommendation that quietly
        grows a second opinion about the machine is how the removed memory
        term would come back, and it went because nobody had a library it
        would have helped.
        """
        jobs = [(i, 'b%d' % i, self.book) for i in range(64)]
        self.assertEqual(scan.recommended_workers(jobs, cap=32), 32)
        self.assertEqual(scan.recommended_workers(jobs, cap=2), 2)

    def test_progress_is_a_fraction_and_a_title(self):
        seen = []
        scan.scan_books(self.binary,
                        [(1, 'One', self.book), (2, 'Two', self.book)],
                        notify=lambda frac, title: seen.append((frac, title)))
        self.assertEqual([t for _f, t in seen], ['One', 'Two'])
        self.assertEqual(seen[0][0], 0.0)
        self.assertTrue(0 < seen[1][0] < 1)


class InstallRecordTests(unittest.TestCase):
    """The shared record, which is what makes one binary serve two plugins."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._real = install.data_dir
        install.data_dir = lambda: self.tmp

    def tearDown(self):
        import shutil
        install.data_dir = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_binary_folder_is_not_the_editor_plugins(self):
        """The separation, pinned.

        Sharing one folder was tried and dropped: a library scan holds the
        binary open for ten minutes and Windows will not let a running
        executable be overwritten, so the editor plugin's hourly update check
        could land in the middle of one. `data_dir` is stubbed for the rest of
        this class, so the real one is read directly.
        """
        from calibre.constants import config_dir
        self.assertEqual(
            self._real(),
            os.path.join(config_dir, 'plugins', 'epubveri-library-data'))

    def test_nothing_writes_to_the_editor_plugins_preferences(self):
        """A shim that did exactly that was removed with the sharing.

        One plugin writing into another's config is the kind of thing that
        surprises somebody a year later, so its absence is worth a test rather
        than a memory.
        """
        import inspect
        source = inspect.getsource(install)
        self.assertNotIn("JSONConfig", source)
        self.assertNotIn("plugins/epubveri'", source)

    def test_an_absent_record_reads_as_empty(self):
        self.assertEqual(install.read_record(), {})

    def test_a_write_merges_rather_than_replaces(self):
        install.write_record(binary_sha256='a')
        install.write_record(last_update_check=7)
        record = install.read_record()
        self.assertEqual(record['binary_sha256'], 'a')
        self.assertEqual(record['last_update_check'], 7)

    def test_a_corrupt_record_does_not_raise(self):
        with open(os.path.join(self.tmp, install.RECORD_NAME), 'w') as handle:
            handle.write('{not json')
        self.assertEqual(install.read_record(), {})

    def test_the_record_is_read_from_disk_every_time(self):
        """The whole point: the other plugin may have rewritten it since.

        A cached copy is precisely the stale hash this file exists to prevent,
        so a write by someone else must be visible immediately.
        """
        install.write_record(binary_sha256='a')
        path = os.path.join(self.tmp, install.RECORD_NAME)
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump({'binary_sha256': 'b'}, handle)
        self.assertEqual(install.read_record()['binary_sha256'], 'b')

    def test_first_sight_of_a_binary_is_trusted_and_recorded(self):
        book = os.path.join(self.tmp, 'pretend-binary')
        with open(book, 'wb') as handle:
            handle.write(b'x' * 10)
        self.assertIsNone(install.integrity_failure(book))
        self.assertTrue(install.read_record()['binary_sha256'])

    def test_a_changed_binary_is_refused(self):
        book = os.path.join(self.tmp, 'pretend-binary')
        with open(book, 'wb') as handle:
            handle.write(b'x' * 10)
        install.integrity_failure(book)
        with open(book, 'wb') as handle:
            handle.write(b'y' * 10)
        message = install.integrity_failure(book)
        self.assertTrue(message and 'has changed' in message)

    def test_stale_note_is_silent_until_a_month_has_passed(self):
        install.write_record(last_update_success=int(time.time()))
        self.assertIsNone(install.stale_note())
        install.write_record(last_update_success=int(time.time()) - 40 * 86400)
        self.assertIn('40 days', install.stale_note())


class DialogTests(PinnedPrefs, unittest.TestCase):

    def _dialog(self, report):
        qt_app()
        from qt.core import QWidget
        from calibre_plugins.epubveri_library.results import ResultsDialog
        self.shown = []
        parent = QWidget()
        dialog = ResultsDialog(parent, report,
                               lambda ids, label: self.shown.append((ids, label)))
        return dialog

    def _report(self):
        report = scan.ScanReport()
        report.scanned = 3
        report.requested = 3
        for book_id in (1, 2):
            report.add(make_finding(severity='error', params=['img']), book_id)
        report.add(make_finding(severity='warning', params=['table']), 3)
        report.add(make_finding(severity='usage', params=['span']), 3)
        return report

    def test_the_table_shows_what_the_filter_admits(self):
        dialog = self._dialog(self._report())
        self.assertEqual(dialog.table.topLevelItemCount(), 2)
        dialog.usage.setChecked(True)
        self.assertEqual(dialog.table.topLevelItemCount(), 3)

    def test_the_most_widespread_row_is_first(self):
        dialog = self._dialog(self._report())
        self.assertEqual(dialog.table.topLevelItem(0).group.books, 2)

    def test_numbers_sort_as_numbers(self):
        """Qt compares display text unless told otherwise, and '1000' sorts
        before '99'."""
        report = scan.ScanReport()
        for book_id in range(12):
            report.add(make_finding(params=['img']), book_id)
        for book_id in range(2):
            report.add(make_finding(params=['table']), book_id)
        dialog = self._dialog(report)
        from qt.core import Qt
        dialog.table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
        self.assertEqual(dialog.table.topLevelItem(0).group.books, 2)
        dialog.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        self.assertEqual(dialog.table.topLevelItem(0).group.books, 12)

    def test_visible_ids_is_the_union_of_the_rows_shown(self):
        dialog = self._dialog(self._report())
        self.assertEqual(dialog._visible_ids(), {1, 2, 3})
        dialog.warnings.setChecked(False)
        self.assertEqual(dialog._visible_ids(), {1, 2})

    def test_show_books_with_no_selection_offers_everything_visible(self):
        dialog = self._dialog(self._report())
        dialog._show_books()
        self.assertEqual(self.shown[0][0], {1, 2, 3})

    def test_show_books_with_a_selection_offers_that_row(self):
        dialog = self._dialog(self._report())
        dialog.table.topLevelItem(0).setSelected(True)
        dialog._show_books()
        self.assertEqual(self.shown[0][0], {1, 2})

    def test_the_csv_carries_the_grouping_fields(self):
        dialog = self._dialog(self._report())
        text = dialog._as_csv()
        self.assertIn('violation_kind', text.splitlines()[0])
        self.assertIn('element_not_allowed', text)

    def test_everything_that_leaves_the_window_says_what_the_scan_was(self):
        """A report is a dated observation (owner, 2026-09-12).

        Which epubveri, which machine, when, how long — beside the findings
        and not only in the window, or a file read next month is a claim with
        no date on it. Asserted on both exports and on the clipboard, because
        three copies of one idea are three chances to forget one.
        """
        report = self._report()
        report.started_at = datetime(2026, 9, 12, 15, 30)
        report.tool_version = '0.14.3'
        report.workers = 8
        report.elapsed = 68.9
        report.machine = [('cores', '10'), ('calibre', '9.14.0')]
        dialog = self._dialog(report)
        for text in (dialog._as_csv(dialog._with_preamble(dialog._as_rows())),
                     dialog._as_csv(dialog._with_preamble(
                         dialog._as_book_rows())),
                     dialog._conditions_text(),
                     dialog.conditions.text()):
            self.assertIn('0.14.3', text)
            self.assertIn('2026-09-12 15:30', text)
            self.assertIn('10', text)

    def test_the_preamble_is_separated_from_the_table(self):
        """A blank row, so nothing reads the two as one block."""
        report = self._report()
        report.started_at = datetime(2026, 9, 12, 15, 30)
        dialog = self._dialog(report)
        lines = dialog._as_csv(
            dialog._with_preamble(dialog._as_rows())).splitlines()
        blank = lines.index('')
        self.assertTrue(lines[blank + 1].startswith('message,'))

    def test_showing_books_leaves_the_window_open(self):
        """maddz's report (MobileRead 375207 #14), as a test.

        The dialog used to `accept()` here, which spent an eight-minute scan
        on one click. `result()` stays 0 and `isVisible()` is not consulted —
        the window is never `show()`n in a test — so what is asserted is that
        the dialog did not finish itself.
        """
        dialog = self._dialog(self._report())
        finished = []
        dialog.finished.connect(finished.append)
        dialog._double_clicked(dialog.table.topLevelItem(0), 0)
        self.assertEqual(self.shown[0][0], {1, 2})
        self.assertEqual(finished, [])

    def test_each_row_hands_over_its_own_books(self):
        """Two rows in succession, each with its own set.

        **Not a guard on the window staying open** — checked by breaking
        `_show_ids` and watching this still pass, because a dialog that has
        accepted still answers a method call in a test. The one that fails is
        the one above; this pins which books a row names.
        """
        dialog = self._dialog(self._report())
        dialog._double_clicked(dialog.table.topLevelItem(0), 0)
        dialog._double_clicked(dialog.table.topLevelItem(1), 0)
        self.assertEqual([ids for ids, _label in self.shown], [{1, 2}, {3}])

    def test_the_book_csv_counts_each_book_separately(self):
        """A defect on two books, forty times in one of them.

        The row-level report cannot say that — it holds one total — and a set
        of book ids could not have carried it either. This is what DNSB asked
        for (MobileRead 375207 #13).
        """
        report = scan.ScanReport()
        report.scanned = 2
        report.requested = 2
        for _ in range(40):
            report.add(make_finding(severity='error', params=['img']), 1)
        report.add(make_finding(severity='error', params=['img']), 2)
        report.books = [scan.BookResult(1, 'Loud', 'a.epub'),
                        scan.BookResult(2, 'Quiet', 'b.epub')]
        dialog = self._dialog(report)
        rows = list(dialog._as_book_rows())
        self.assertEqual(rows[0][:2], ('book_id', 'title'))
        self.assertEqual([(r[1], r[7]) for r in rows[1:]],
                         [('Loud', 40), ('Quiet', 1)])

    def test_the_book_csv_obeys_the_filter_the_window_shows(self):
        report = self._report()
        report.books = [scan.BookResult(book_id, 'B%d' % book_id, 'x.epub')
                        for book_id in (1, 2, 3)]
        dialog = self._dialog(report)
        self.assertEqual(len(list(dialog._as_book_rows())), 4)   # header + 3
        dialog.warnings.setChecked(False)
        self.assertEqual(len(list(dialog._as_book_rows())), 3)   # header + 2

    def test_the_summary_names_the_scan(self):
        dialog = self._dialog(self._report())
        self.assertIn('3 books scanned', dialog.summary.text())

    def test_a_cancelled_scan_says_so(self):
        report = self._report()
        report.cancelled = True
        report.scanned = 1
        dialog = self._dialog(report)
        self.assertIn('Cancelled after 1 of 3', dialog.summary.text())


class StoreTests(unittest.TestCase):
    """Writing a report and reading it back.

    **Pointed at a temporary directory**, because `store` resolves its path
    through `install.data_dir()`, which is the *running* calibre's config
    folder. A suite that used it would write into the settings of whoever ran
    the tests — the mistake `PinnedPrefs` exists for, one directory along.
    """

    def setUp(self):
        import calibre_plugins.epubveri_library.store as store
        self.store = store
        self.tmp = tempfile.mkdtemp()
        self._saved = store.data_dir
        store.data_dir = lambda create=True: self.tmp

    def tearDown(self):
        self.store.data_dir = self._saved

    def _report(self):
        report = scan.ScanReport()
        report.requested = 3
        report.scanned = 3
        report.elapsed = 12.5
        report.workers = 4
        report.tool_version = '0.14.3'
        report.started_at = datetime(2026, 9, 12, 15, 30)
        report.machine = [('system', 'macOS 26.6.2'), ('cores', '10')]
        for book_id in (11, 12):
            report.add(make_finding(severity='error', params=['img']), book_id)
        report.add(make_finding(severity='error', params=['img']), 11)
        report.add(make_finding(severity='warning', params=['table']), 13)
        report.books = [scan.BookResult(book_id, 'B%d' % book_id, '/x.epub')
                        for book_id in (11, 12, 13)]
        report.no_format.append(scan.BookResult(14, 'No EPUB', None))
        return report

    def test_a_saved_report_comes_back_the_same_report(self):
        """Asserted through the window rather than through the dict it was
        written from, which would only prove the writer agrees with itself."""
        qt_app()
        from qt.core import QWidget
        from calibre_plugins.epubveri_library.results import ResultsDialog
        original = self._report()
        self.assertTrue(self.store.save('lib-1', original))
        restored = self.store.load('lib-1')
        self.assertIsNotNone(restored)
        parent = QWidget()
        nothing = lambda ids, label: None                # noqa: E731
        before = ResultsDialog(parent, original, nothing)
        after = ResultsDialog(parent, restored, nothing)
        self.assertEqual(after._as_csv(after._with_preamble(after._as_rows())),
                         before._as_csv(before._with_preamble(before._as_rows())))
        self.assertEqual(
            after._as_csv(after._with_preamble(after._as_book_rows())),
            before._as_csv(before._with_preamble(before._as_book_rows())))

    def test_book_ids_come_back_as_numbers(self):
        """JSON object keys are strings whatever they went in as, and a string
        book id marks nothing — `set_marked_ids` would file it under a book
        that does not exist and the search would come back empty."""
        self.store.save('lib-1', self._report())
        restored = self.store.load('lib-1')
        for group in restored.groups.values():
            for book_id in group.book_counts:
                self.assertIsInstance(book_id, int)

    def test_the_unreadable_list_is_rebuilt_rather_than_stored(self):
        report = self._report()
        report.books[1].status = 'failed'
        report.books[1].error = 'could not be read'
        report.unreadable.append(report.books[1])
        self.store.save('lib-1', report)
        restored = self.store.load('lib-1')
        self.assertEqual([r.book_id for r in restored.unreadable], [12])
        self.assertEqual(len(restored.no_format), 1)

    def test_saving_demotes_the_last_scan(self):
        first = self._report()
        first.tool_version = 'first'
        second = self._report()
        second.tool_version = 'second'
        self.store.save('lib-1', first)
        self.store.save('lib-1', second)
        self.assertEqual(self.store.load('lib-1').tool_version, 'second')
        self.assertEqual(
            self.store.load('lib-1', self.store.PREVIOUS).tool_version,
            'first')

    def test_each_library_has_its_own_slots(self):
        """The one guard that is structural: a report cannot be shown against
        another library's books, because it is not there to load."""
        self.store.save('lib-1', self._report())
        self.assertIsNone(self.store.load('lib-2'))
        self.assertFalse(self.store.exists('lib-2'))

    def test_a_file_this_code_cannot_read_is_the_same_as_no_file(self):
        self.store.save('lib-1', self._report())
        path = self.store._path('lib-1', self.store.CURRENT)
        import gzip
        with gzip.open(path, 'wb') as handle:
            handle.write(b'{"format": 999}')
        self.assertIsNone(self.store.load('lib-1'))

    def test_a_truncated_file_is_the_same_as_no_file(self):
        """A scan interrupted mid-write. `load` may not raise into a menu."""
        self.store.save('lib-1', self._report())
        path = self.store._path('lib-1', self.store.CURRENT)
        with open(path, 'wb') as handle:
            handle.write(b'\x1f\x8b\x08truncated')
        self.assertIsNone(self.store.load('lib-1'))

    def test_the_scope_survives_a_round_trip(self):
        """Which matters because only one scope may become a baseline."""
        report = self._report()
        report.scope = 'selection'
        self.store.save('lib-1', report)
        self.assertEqual(self.store.load('lib-1').scope, 'selection')

    def test_asking_whether_a_report_exists_creates_nothing(self):
        """The menu asks this every time it opens. A plugin that has been
        installed and never used should leave nothing behind."""
        import os as _os
        empty = tempfile.mkdtemp()
        self.store.data_dir = lambda create=True: empty
        self.assertFalse(self.store.exists('lib-1'))
        self.assertIsNone(self.store.load('lib-1'))
        self.assertEqual(_os.listdir(empty), [])

    def test_it_can_say_how_much_it_is_keeping_and_stop(self):
        """A stored report holds book titles, so a user is owed both."""
        self.store.save('lib-1', self._report())
        self.store.save('lib-1', self._report())
        self.store.save('lib-2', self._report())
        files, total = self.store.stored_size()
        self.assertEqual(files, 3)
        self.assertGreater(total, 0)
        self.assertEqual(self.store.forget_all(), 3)
        self.assertEqual(self.store.stored_size(), (0, 0))
        self.assertIsNone(self.store.load('lib-1'))

    def test_saving_never_takes_a_scan_down_with_it(self):
        self.store.data_dir = lambda create=True: '/dev/null/not-a-directory'
        self.assertFalse(self.store.save('lib-1', self._report()))
        self.assertIsNone(self.store.load('lib-1'))
        self.assertFalse(self.store.exists('lib-1'))


class CompareTests(unittest.TestCase):

    def _report(self, rows, tool_version='0.14.3'):
        """`rows` is `{construct: [book_id, ...]}`."""
        report = scan.ScanReport()
        report.tool_version = tool_version
        report.scanned = 9
        for name, book_ids in rows.items():
            for book_id in book_ids:
                report.add(make_finding(severity='error', params=[name]),
                           book_id)
        return report

    def _comparison(self, before, after):
        from calibre_plugins.epubveri_library.compare import Comparison
        return Comparison(before, after)

    def test_it_says_which_way_each_rule_went(self):
        comparison = self._comparison(
            self._report({'img': [1, 2, 3], 'table': [4], 'gone': [5]}),
            self._report({'img': [1], 'table': [4, 6], 'new': [7]}))
        states = {change.group.name: change.state
                  for change in comparison.changes}
        self.assertEqual(states, {'img': 'better', 'table': 'worse',
                                  'gone': 'gone', 'new': 'new'})

    def test_the_biggest_movement_comes_first_and_the_still_rows_last(self):
        """Not the report's ordering. A row on 400 books that did not move is
        the least interesting line in a comparison."""
        comparison = self._comparison(
            self._report({'still': list(range(400)), 'img': [1, 2, 3]}),
            self._report({'still': list(range(400)), 'img': [1]}))
        self.assertEqual([c.group.name for c in comparison.changes],
                         ['img', 'still'])

    def test_it_counts_rules_rather_than_findings(self):
        comparison = self._comparison(
            self._report({'img': [1, 2], 'table': [3]}),
            self._report({'img': [1], 'table': [3, 4]}))
        self.assertEqual(comparison.moved(), (1, 1))

    def test_books_touched_ignores_rules_that_did_not_move(self):
        comparison = self._comparison(
            self._report({'still': [9], 'img': [1, 2]}),
            self._report({'still': [9], 'img': [1]}))
        self.assertEqual(comparison.books_touched(), {1, 2})

    def test_two_versions_of_epubveri_are_not_the_same_validator(self):
        same = self._comparison(self._report({'img': [1]}),
                                self._report({'img': [1]}))
        self.assertTrue(same.same_validator)
        moved = self._comparison(
            self._report({'img': [1]}, tool_version='0.14.2'),
            self._report({'img': [1]}, tool_version='0.14.3'))
        self.assertFalse(moved.same_validator)

    def test_an_unknown_version_is_not_agreement(self):
        """An older stored report may carry no version at all, and silence is
        not the same as a match."""
        comparison = self._comparison(self._report({'img': [1]}, ''),
                                      self._report({'img': [1]}, ''))
        self.assertFalse(comparison.same_validator)


class CompareDialogTests(PinnedPrefs, unittest.TestCase):

    def _dialog(self, before, after):
        qt_app()
        from qt.core import QWidget
        from calibre_plugins.epubveri_library.compare import Comparison
        from calibre_plugins.epubveri_library.results import CompareDialog
        self.shown = []
        return CompareDialog(
            QWidget(), Comparison(before, after),
            lambda ids, label: self.shown.append((ids, label)))

    def _report(self, rows, tool_version='0.14.3'):
        report = scan.ScanReport()
        report.tool_version = tool_version
        report.scanned = 9
        report.started_at = datetime(2026, 9, 12, 15, 30)
        for name, book_ids in rows.items():
            for book_id in book_ids:
                report.add(make_finding(severity='error', params=[name]),
                           book_id)
        return report

    def test_unmoved_rules_are_hidden_until_asked_for(self):
        dialog = self._dialog(self._report({'still': [9], 'img': [1, 2]}),
                              self._report({'still': [9], 'img': [1]}))
        self.assertEqual(dialog.table.topLevelItemCount(), 1)
        dialog.unchanged.setChecked(True)
        self.assertEqual(dialog.table.topLevelItemCount(), 2)

    def test_the_window_and_its_export_agree_about_the_order(self):
        """Found by running a real before/after, not by reading the code.

        The first version enabled sorting without naming a column; Qt sorted on
        the message id and the table came out in a different order from the CSV
        the same window writes. Two orders for one set of rows is the kind of
        thing nobody notices until they are comparing the two artefacts.
        """
        before = self._report({'a': [1, 2, 3, 4], 'b': [1, 2], 'c': [1]})
        after = self._report({'a': [1], 'b': [1, 2, 3], 'c': [1]})
        dialog = self._dialog(before, after)
        dialog.unchanged.setChecked(True)
        shown = [dialog.table.topLevelItem(i).change
                 for i in range(dialog.table.topLevelItemCount())]
        self.assertEqual([c.group.name for c in shown],
                         [c.group.name for c in dialog._rows()])
        # And that order is by how far a row moved, with the still one last.
        self.assertEqual([c.group.name for c in shown], ['a', 'b', 'c'])

    def test_a_different_validator_is_said_out_loud(self):
        """The confound this window cannot resolve, so it names it."""
        quiet = self._dialog(self._report({'img': [1, 2]}),
                             self._report({'img': [1]}))
        self.assertEqual(quiet.caveat.text(), '')
        loud = self._dialog(self._report({'img': [1, 2]}, '0.14.2'),
                            self._report({'img': [1]}, '0.14.3'))
        self.assertIn('different versions', loud.caveat.text())

    def test_the_summary_dates_both_scans(self):
        dialog = self._dialog(self._report({'img': [1, 2]}),
                              self._report({'img': [1]}))
        self.assertIn('1 rule better, 0 worse', dialog.summary.text())
        self.assertIn('2026-09-12 15:30', dialog.summary.text())

    def test_the_csv_carries_both_scans_conditions(self):
        dialog = self._dialog(self._report({'img': [1, 2]}, '0.14.2'),
                              self._report({'img': [1]}, '0.14.3'))
        rows = list(dialog._preamble())
        labels = [row[0] for row in rows if row]
        self.assertIn('before epubveri', labels)
        self.assertIn('after epubveri', labels)

    def test_showing_books_leaves_the_window_open(self):
        dialog = self._dialog(self._report({'img': [1, 2]}),
                              self._report({'img': [1]}))
        finished = []
        dialog.finished.connect(finished.append)
        dialog._show_books()
        self.assertEqual(self.shown[0][0], {1, 2})
        self.assertEqual(finished, [])


class ActionTests(unittest.TestCase):
    """Importing `action` is itself the test worth having here.

    It is the module full of calibre and Qt names, and two of them were wrong
    before this suite existed: a `JobManager.get_group_count` that does not
    exist in calibre 9.14, and `db.set_marked_ids`, which lives on `db.data`.
    Neither would have shown up before a user clicked the button.
    """

    def test_it_imports(self):
        qt_app()
        import calibre_plugins.epubveri_library.action as action
        self.assertTrue(action.EpubveriLibraryAction.name)

    def test_the_search_string_is_an_exact_match(self):
        import calibre_plugins.epubveri_library.action as action
        # A bare `marked:epubveri` is a substring match and would also select
        # whatever another plugin had marked `epubveri-something`.
        self.assertEqual(action.MARK_SEARCH, 'marked:"=epubveri"')

    def test_every_report_method_is_reachable_from_the_menu(self):
        """The defect that produced this release, as a test.

        `show_last_report`, `show_books_without_epub` and `clear_marks` were
        written for 0.1.0 with their reasoning, and `genesis` never mentioned
        them — so the menu had two entries and the source had five answers.
        Nothing failed, because dead code does not.

        Read out of the source rather than off a running calibre: `genesis`
        needs a real GUI, and the question here is whether the wiring is
        *written*, which the text answers exactly.
        """
        import ast
        path = os.path.join(PLUGIN_DIR, 'action.py')
        with open(path, encoding='utf-8') as handle:
            tree = ast.parse(handle.read(), path)
        cls = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef)
                   and node.name == 'EpubveriLibraryAction')
        genesis = next(node for node in cls.body
                       if isinstance(node, ast.FunctionDef)
                       and node.name == 'genesis')
        wired = {node.attr for node in ast.walk(genesis)
                 if isinstance(node, ast.Attribute)}
        for name in ('show_last_report', 'show_books_without_epub',
                     'clear_marks'):
            self.assertIn(name, wired,
                          '%s is defined and nothing can reach it' % name)

    def test_clear_marks_can_find_the_marks_it_left(self):
        """`_marked_ids` did not exist while `clear_marks` was calling it.

        Nothing caught that because the menu entry reaching `clear_marks` was
        never connected, so the method had never run. The stub offers the
        calibre 9.14 spelling only — `marked_ids` on the *view*, an instance
        attribute rather than a class one — so a wrong path fails here.
        """
        import calibre_plugins.epubveri_library.action as action

        class Data(object):
            marked_ids = {3: 'epubveri', 4: 'somebody else', 5: 'epubveri'}

        class DB(object):
            data = Data()

        stub = type('Stub', (), {'gui': type('G', (), {'current_db': DB()})()})()
        found = action.EpubveriLibraryAction._marked_ids(stub)
        self.assertEqual(found, {3, 5})

    def test_marked_ids_is_empty_rather_than_angry_with_no_library(self):
        """The menu asks this before anything is open."""
        import calibre_plugins.epubveri_library.action as action
        stub = type('Stub', (), {'gui': type('G', (), {})()})()
        self.assertEqual(action.EpubveriLibraryAction._marked_ids(stub), set())

    def test_neither_half_of_the_button_starts_a_scan(self):
        """The button keeps calibre's drop-down arrow, which needs
        `MenuButtonPopup` — and that mode wires the button's body to the
        action. So the arrow is only safe while that connection goes to the
        menu; `triggered` reaching `start` or `repeat_last` would put ten
        minutes of work behind a stray click again.
        """
        import ast
        from qt.core import QToolButton
        import calibre_plugins.epubveri_library.action as action
        self.assertIs(action.EpubveriLibraryAction.popup_type,
                      QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        path = os.path.join(PLUGIN_DIR, 'action.py')
        with open(path, encoding='utf-8') as handle:
            tree = ast.parse(handle.read(), path)
        cls = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef)
                   and node.name == 'EpubveriLibraryAction')
        genesis = next(node for node in cls.body
                       if isinstance(node, ast.FunctionDef)
                       and node.name == 'genesis')
        connected = [node.args[0] for node in ast.walk(genesis)
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute)
                     and node.func.attr == 'connect' and node.args]
        targets = {node.attr for node in connected
                   if isinstance(node, ast.Attribute)}
        self.assertIn('show_menu', targets)
        self.assertNotIn('start', targets)
        self.assertNotIn('repeat_last', targets)

    def test_only_a_whole_library_scan_becomes_a_baseline(self):
        """A five-book selection opposite a three-thousand-book scan reads as
        a library that was almost entirely repaired. Read out of the source,
        since `finished` needs a calibre GUI to run."""
        import ast
        path = os.path.join(PLUGIN_DIR, 'action.py')
        with open(path, encoding='utf-8') as handle:
            tree = ast.parse(handle.read(), path)
        cls = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef)
                   and node.name == 'EpubveriLibraryAction')
        finished = next(node for node in cls.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == 'finished')
        saves = [node for node in ast.walk(finished)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and node.func.attr == 'save']
        self.assertEqual(len(saves), 1)
        guards = [node for node in ast.walk(finished) if isinstance(node, ast.If)
                  and any(isinstance(c, ast.Call)
                          and isinstance(c.func, ast.Attribute)
                          and c.func.attr == 'save'
                          for c in ast.walk(node))]
        self.assertTrue(guards, 'store.save is not behind a scope check')
        self.assertIn('scope', ast.dump(guards[-1].test))

    def test_show_books_marks_through_db_data(self):
        """The line that would have crashed, exercised rather than reasoned about.

        `db.data.set_marked_ids` is the calibre 9.14 spelling; the widely
        copied `db.set_marked_ids` raises AttributeError. A stub that offers
        only the correct path is what makes the wrong one fail here instead of
        under somebody's mouse.
        """
        import calibre_plugins.epubveri_library.action as action

        marked = {}

        class Data(object):
            def set_marked_ids(self, id_dict):
                marked.update(id_dict)

        class DB(object):
            def __init__(self):
                self.data = Data()

        searched, messages = [], []

        class Gui(object):
            def __init__(self):
                self.current_db = DB()
                self.search = type('S', (), {
                    'set_search_string': staticmethod(searched.append)})()
                self.status_bar = type('B', (), {
                    'show_message': staticmethod(
                        lambda text, ms=0: messages.append(text))})()

        stub = type('Stub', (), {'gui': Gui()})()
        action.EpubveriLibraryAction.show_books(stub, {3, 4}, 'RSC-005')
        self.assertEqual(marked, {3: 'epubveri', 4: 'epubveri'})
        self.assertEqual(searched, ['marked:"=epubveri"'])
        self.assertIn('2 books', messages[0])

    def test_the_job_callback_is_marshalled_to_the_gui_thread(self):
        """The crash, pinned.

        `ThreadedJob` calls its callback from the worker thread — `start_work`
        ends `self.callback(self)` inside `ThreadedJobWorker.run`. `finished`
        builds a dialog, so passed as a bare bound method it builds a QWidget
        off the GUI thread and takes calibre down. It did, on the first real
        run. `Dispatcher` is calibre's own answer (`gui2/email.py` does the
        same) and this asserts it is still there.
        """
        qt_app()
        import calibre_plugins.epubveri_library.action as action
        from calibre.gui2 import Dispatcher

        stub = type('Stub', (), {'finished': lambda self, job: None})()
        callback = action.EpubveriLibraryAction.dispatched_finish(stub)
        self.assertIsInstance(callback, Dispatcher)

    def test_the_button_says_what_it_does_not_who_made_it(self):
        """The label was a bare "epubveri" and that was the whole complaint.

        calibre's toolbar row is verbs — Add books, Edit metadata, Convert
        books, Remove books, Tweak ePub — and the editor plugin's button says
        "Validate with epubveri". A bare brand name sat wrong among the first
        and was indistinguishable from the second.
        """
        import calibre_plugins.epubveri_library.action as action
        label = action.EpubveriLibraryAction.action_spec[0]
        self.assertEqual(label, 'Validate library')
        self.assertNotEqual(label.lower(), 'epubveri')
        # The brand still has somewhere to live: the tooltip.
        self.assertIn('epubveri', action.EpubveriLibraryAction.action_spec[2])

    def test_the_plugin_name_cannot_collide_with_the_editor_plugin(self):
        """`name` is calibre's identity key, not a caption.

        `gprefs['action-layout-*']` stores it, and two plugins answering to one
        name would fight over every placement. It is also what a rename
        orphans, which is why this is pinned rather than left to care.
        """
        from calibre_plugins.epubveri_library import PLUGIN_NAME
        self.assertEqual(PLUGIN_NAME, 'epubveri library')
        self.assertNotEqual(PLUGIN_NAME, 'epubveri')
        # `check` is the word in `epubcheck`, W3C's mark.
        self.assertNotIn('check', PLUGIN_NAME.lower())

    def test_it_is_listed_as_the_gui_plugin_it_is(self):
        """It takes its own base class's category, and that is a reversal.

        Until 0.2.0 this was forced to `EditBookToolPlugin.type` so the two
        plugins would share one heading in Preferences / Plugins — one
        product, one place. The cost was known and written down: this plugin
        never appears in Edit Book, so the heading named where its *sibling*
        lived.

        MobileRead settled it the other way. A moderator retitled the thread
        **[GUI Plugin] epubveri library** and Comfy.n filed it under *Extend
        calibre generally* (375207 #3, #6, #7) — the calibre community
        answering the same question about the same plugin. A Preferences entry
        saying "Edit book tool" would now disagree with the index the user
        found it in.

        Nothing functional turns on the value, which is what made the override
        safe and what makes this test the only thing that would notice it
        coming back.
        """
        from calibre.customize import EditBookToolPlugin, InterfaceActionBase
        from calibre_plugins.epubveri_library import EpubveriLibraryPlugin
        self.assertEqual(EpubveriLibraryPlugin.type, InterfaceActionBase.type)
        self.assertNotEqual(EpubveriLibraryPlugin.type, EditBookToolPlugin.type)

    def test_the_list_description_is_one_line(self):
        """It ran to three lines in a column of one-liners. calibre's own are
        around fifty characters — "Copy a book from one calibre library to
        another" — so this is held to that order of length."""
        from calibre_plugins.epubveri_library import EpubveriLibraryPlugin
        description = EpubveriLibraryPlugin.description
        self.assertLessEqual(len(description), 90, description)
        self.assertNotIn('.', description[:-1],
                         'more than one sentence: %s' % description)

    def test_the_apis_it_calls_exist(self):
        """Each of these was checked against calibre 9.14's source once. This
        makes the next calibre the thing that tells us, rather than a user."""
        from calibre.gui2.jobs import JobManager
        from calibre.gui2.library.models import BooksModel
        from calibre.db.view import View
        from calibre.db.legacy import LibraryDatabase
        from calibre.gui2.ui import Main
        self.assertTrue(hasattr(JobManager, 'run_threaded_job'))
        self.assertTrue(hasattr(JobManager, 'unfinished_jobs'))
        self.assertTrue(hasattr(BooksModel, 'id'))
        self.assertTrue(hasattr(View, 'set_marked_ids'))
        self.assertTrue(hasattr(LibraryDatabase, 'all_ids'))
        self.assertTrue(hasattr(LibraryDatabase, 'format_abspath'))
        self.assertTrue(hasattr(Main, 'job_exception'))


class ConfigTests(PinnedPrefs, unittest.TestCase):

    def test_errors_and_fatals_cannot_be_switched_off(self):
        """A report that can be configured to hide what decides a verdict is
        not a validator's report."""
        for warning in (True, False):
            for usage in (True, False):
                cfg.prefs['show_warning'] = warning
                cfg.prefs['show_usage'] = usage
                levels = cfg.severities()
                self.assertIn('error', levels)
                self.assertIn('fatal', levels)

    def test_usage_and_advisory_are_off_by_default(self):
        self.assertFalse(cfg.prefs.defaults['show_usage'])
        self.assertFalse(cfg.prefs.defaults['show_advisory'])
        self.assertTrue(cfg.prefs.defaults['show_warning'])


class ConfigWidgetTests(PinnedPrefs, unittest.TestCase):
    """The settings page, built and saved.

    **A tabbed page is exactly the refactor that drops a control silently**:
    move a checkbox into a tab, forget its line in `save_settings`, and the
    setting stops being saved with nothing failing anywhere. So this flips
    every control away from its default, saves, and reads the file back.
    """

    def _widget(self):
        qt_app()
        return cfg.ConfigWidget()

    def test_there_is_no_tab_widget(self):
        """A tabbed version of this page shipped and was withdrawn: clicking
        one tab dropped calibre's modal Customize dialog behind the
        Preferences window on the owner's machine, and it was never reproduced
        here. The dialog is calibre's; what goes inside it is ours, so the
        component went. See the class docstring before putting it back."""
        from qt.core import QTabWidget
        self.assertIsNone(self._widget().findChild(QTabWidget))

    def test_it_stays_short_enough_for_the_dialog_it_opens_in(self):
        """The height that caused all of this. calibre's dialog wraps the page
        in a scroll area, so an over-tall page is a scrollbar rather than a
        bigger window — and an over-*wide* one is a horizontal scrollbar,
        which is worse because nothing suggests scrolling sideways."""
        widget = self._widget()
        # The bound is the version that was too tall: four framed group boxes
        # came to 432 px. Anything at or above that has undone the fix.
        self.assertLess(widget.sizeHint().height(), 400)
        self.assertLess(widget.minimumSizeHint().width(), 500)

    def test_the_spin_box_fits_the_word_it_shows(self):
        """It showed "utomatic (8)". A `QSpinBox` sizes itself to its number
        range and not to its special value text, and the range here is 0-8."""
        widget = self._widget()
        text = widget.workers.specialValueText()
        self.assertGreater(
            widget.workers.minimumWidth(),
            widget.workers.fontMetrics().horizontalAdvance(text))

    def test_every_long_explanation_is_reachable(self):
        """The paragraphs became tooltips; a tooltip nobody set is an
        explanation that was deleted rather than moved."""
        widget = self._widget()
        for control in (widget.show_warning, widget.show_usage,
                        widget.show_advisory, widget.autoupdate,
                        widget.workers, widget.forget):
            self.assertTrue(control.toolTip().strip(), control)

    def test_each_section_says_something_before_you_hover(self):
        """Bare headings read as *çok sade* — a column of words with no hint
        what ranking a usage note would do to you. One dimmed line a section
        is the middle term between that and the paragraphs that made the page
        too tall."""
        from qt.core import QLabel
        widget = self._widget()
        captions = [label for label in widget.findChildren(QLabel)
                    if label.wordWrap()]
        self.assertGreaterEqual(len(captions), 4)
        for caption in captions:
            self.assertTrue(caption.text().strip())

    def test_every_control_still_reaches_the_settings_file(self):
        widget = self._widget()
        widget.show_warning.setChecked(False)
        widget.show_usage.setChecked(True)
        widget.show_advisory.setChecked(True)
        widget.autoupdate.setChecked(False)
        widget.workers.setValue(1)
        widget.save_settings()
        self.assertFalse(cfg.as_bool(cfg.prefs['show_warning']))
        self.assertTrue(cfg.as_bool(cfg.prefs['show_usage']))
        self.assertTrue(cfg.as_bool(cfg.prefs['show_advisory']))
        self.assertFalse(cfg.as_bool(cfg.prefs['autoupdate']))
        self.assertEqual(cfg.prefs['workers'], 1)

    def test_a_few_kilobytes_is_not_shown_as_zero_megabytes(self):
        """Which is what it said, right above a button offering to delete it.

        Real saved scans are kilobytes — 20 KB for a 474-book library — and
        `0.0 MB` reads as *nothing is stored*. The megabyte unit came from the
        18 000-book estimate, where it is right.
        """
        import calibre_plugins.epubveri_library.store as store
        widget = self._widget()
        saved = store.stored_size
        try:
            store.stored_size = lambda: (2, 7 * 1024)
            widget._show_saved_size()
            self.assertIn('7 KB', widget.saved_note.text())
            store.stored_size = lambda: (2, 3 * 1024 * 1024)
            widget._show_saved_size()
            self.assertIn('3.0 MB', widget.saved_note.text())
        finally:
            store.stored_size = saved

    def test_it_opens_on_what_is_already_saved(self):
        cfg.prefs['show_usage'] = True
        cfg.prefs['show_warning'] = False
        widget = self._widget()
        self.assertTrue(widget.show_usage.isChecked())
        self.assertFalse(widget.show_warning.isChecked())


class EnvelopeTests(unittest.TestCase):

    def test_a_multi_input_envelope_is_not_what_this_plugin_reads(self):
        """One process per book, so `Envelope` reading `inputs[0]` is correct.

        Pinned because epubveri *does* accept several `-i` inputs and a future
        change to batch them would silently report the first book's findings
        for every book.
        """
        doc = {'tool_version': '9.9.9', 'status': 'ok', 'inputs': [
            {'path': 'a.epub', 'status': 'ok', 'summary': {}, 'items': []},
            {'path': 'b.epub', 'status': 'problems', 'summary': {'error': 1},
             'items': [{'code': 'X-1', 'severity': 'error', 'message': 'm'}]}]}
        envelope = parse_envelope(json.dumps(doc))
        self.assertEqual(envelope.findings, [])
        self.assertTrue(envelope.is_valid)


def run():
    """Build the suite from this module's namespace.

    `unittest.main()` collects nothing under `calibre-debug`, which runs a
    script in a fresh globals dict, and prints "NO TESTS RAN" rather than
    failing — the sort of green that means nothing.
    """
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for obj in list(globals().values()):
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
            suite.addTests(loader.loadTestsFromTestCase(obj))
    if not suite.countTestCases():
        raise SystemExit('no tests were collected — the suite is not running')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    run()
