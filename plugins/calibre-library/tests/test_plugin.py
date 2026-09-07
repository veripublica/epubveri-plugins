# epubveri library check — tests
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

    KEYS = ('show_warning', 'show_usage', 'show_advisory', 'autoupdate',
            'scope')

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

    def test_the_summary_names_the_scan(self):
        dialog = self._dialog(self._report())
        self.assertIn('3 books scanned', dialog.summary.text())

    def test_a_cancelled_scan_says_so(self):
        report = self._report()
        report.cancelled = True
        report.scanned = 1
        dialog = self._dialog(report)
        self.assertIn('Cancelled after 1 of 3', dialog.summary.text())


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
