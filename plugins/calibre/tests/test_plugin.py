# epubveri for calibre — tests
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Run these inside calibre's own interpreter, which is where the plugin runs:

    /Applications/calibre.app/Contents/MacOS/calibre-debug \\
        plugins/calibre/tests/test_plugin.py

`calibre-debug` executes a script with calibre importable, so the container
API is exercised against a real book rather than a mock. Nothing here touches
the network, and nothing installs the plugin: the import shim below points
`calibre_plugins.epubveri` at the working tree, so the tests read the source
you are editing and not whatever happens to be installed.

**These tests cannot see the things that have actually broken this plugin.**
All three of its defects so far — the `is_customizable` gate, the binary being
installed into the plugin archive, and the settings page — were found by a
person clicking in calibre. A test that could have caught the second one is
here now; the habit is to add one each time, not to believe the suite.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TESTS_DIR)
ROOT = os.path.dirname(os.path.dirname(PLUGIN_DIR))

# Resolve `calibre_plugins.epubveri` to the working tree. calibre installs a
# real import hook for that package name; this stands in for it so the tests
# need no installed copy — and so they can never accidentally test one.
_pkg = sys.modules.setdefault('calibre_plugins',
                              types.ModuleType('calibre_plugins'))
if not hasattr(_pkg, '__path__'):
    _pkg.__path__ = []
_sub = types.ModuleType('calibre_plugins.epubveri')
_sub.__path__ = [PLUGIN_DIR]
sys.modules['calibre_plugins.epubveri'] = _sub

import calibre_plugins.epubveri.main as plugin           # noqa: E402

# The same book the Sigil plugin's tests use, so a disagreement between the
# two plugins is about the plugin and never about the fixture. It is EPUB 3
# and carries a `dcterms:modified`, which is what makes the packaging test
# able to fail.
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
    <item id="spare" href="Misc/spare.xml" media-type="application/xml"/>
  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>"""

NAV = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" '
       'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>T</title></head><body>'
       '<nav epub:type="toc"><ol><li><a href="Text/ch1.xhtml">Ch1</a></li></ol></nav>'
       '</body></html>')
CH1 = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">'
       '<head><title>t</title>'
       '<style type="text/css">p { colour: red }</style></head>'
       '<body><p fake="x">x</p></body></html>')
CONTAINER = ('<?xml version="1.0"?>\n<container version="1.0" '
             'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
             '<rootfile full-path="OEBPS/content.opf" '
             'media-type="application/oebps-package+xml"/></rootfiles></container>')

FILES = {
    'mimetype': 'application/epub+zip',
    'META-INF/container.xml': CONTAINER,
    'OEBPS/content.opf': OPF,
    'OEBPS/nav.xhtml': NAV,
    'OEBPS/Text/ch1.xhtml': CH1,
    'OEBPS/Misc/spare.xml': '<r/>',
}


def build_epub(path):
    """A real OCF container: `mimetype` first and stored, as OCF requires."""
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo('mimetype'), FILES['mimetype'],
                    compress_type=zipfile.ZIP_STORED)
        for name, text in FILES.items():
            if name != 'mimetype':
                zf.writestr(name, text)
    return path


def sha(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def binary():
    path = os.environ.get('EPUBVERI_BINARY') or plugin._binary_path()
    return path if os.path.isfile(path) else None


class Finding(object):
    """Just enough of an envelope finding for the display and result layers."""

    def __init__(self, severity, advisory=False, location='OEBPS/x.xhtml',
                 line=3, column=5, code='RSC-005', message='something'):
        self.severity = severity
        self.is_advisory = advisory
        self.location = location
        self.line = line
        self.column = column
        self.code = code
        self.message = message


_app = None


def qt_app():
    """One QApplication for the whole run; Qt allows no more."""
    global _app
    if _app is None:
        from calibre.gui2 import Application
        _app = Application([])
    return _app


class StubKeyboard(object):
    def __init__(self):
        self.registered = []

    def register_shortcut(self, unique_name, short_text, **kwargs):
        self.registered.append(unique_name)


def stub_tool():
    """An `EpubVeriTool` with a window and a keyboard but no editor.

    `Tool.gui` and `Tool.boss` are properties that reach for a live editor, so
    they are overridden rather than stubbed by assignment.
    """
    from qt.core import QWidget
    qt_app()
    window = QWidget()
    window.keyboard = StubKeyboard()

    class Stubbed(plugin.EpubVeriTool):
        @property
        def gui(self):
            return window

        @property
        def boss(self):
            return None

    tool = Stubbed()
    tool.window = window
    return tool


class DataDirTests(unittest.TestCase):
    """Where the binary goes, which is the one thing about this plugin that
    Sigil's answer gets wrong."""

    def test_the_binary_never_lands_inside_the_plugin_archive(self):
        """calibre imports a plugin out of its zip and never unpacks it, so
        `os.path.dirname(__file__)` is a **file**. Installing there failed
        with `[Errno 17] File exists` — the installer creating a directory
        over the archive it was running from. Sigil unpacks, which is why the
        identical line is correct there and wrong here."""
        data = plugin._data_dir()
        self.assertTrue(os.path.isdir(data), data)
        self.assertFalse(data.endswith('.zip'))
        self.assertFalse(zipfile.is_zipfile(data) if os.path.isfile(data)
                         else False)
        self.assertTrue(plugin._binary_path().startswith(data + os.sep))

    def test_it_is_beside_the_archive_and_not_in_the_plugin_source(self):
        from calibre.constants import config_dir
        self.assertEqual(
            os.path.normpath(plugin._data_dir()),
            os.path.normpath(os.path.join(config_dir, 'plugins', 'epubveri')))
        self.assertNotEqual(os.path.normpath(plugin._data_dir()),
                            os.path.normpath(PLUGIN_DIR))


class PolicyTests(unittest.TestCase):
    """The update and integrity rules, which are the Sigil plugin's rules and
    must not drift from them."""

    def test_a_setting_can_be_a_bool_or_the_words_a_person_types(self):
        for value in (True, 'yes', 'true', 'ON', '1', 'y'):
            self.assertTrue(plugin._as_bool(value), value)
        for value in (False, 'no', 'false', 'off', '0', 'maybe', ''):
            self.assertFalse(plugin._as_bool(value), value)
        self.assertTrue(plugin._as_bool(None))          # first run: default on

    def test_a_stamp_written_before_timezones_is_still_readable(self):
        """Reading a naive stamp as UTC rather than discarding it keeps an
        upgrade from forcing a check on every existing install."""
        from datetime import timedelta
        naive = (plugin._now().replace(tzinfo=None)
                 - timedelta(minutes=5)).isoformat()
        age = plugin._since(naive)
        self.assertIsNotNone(age)
        self.assertLess(age, timedelta(hours=1))
        self.assertIsNone(plugin._since('not a date'))
        self.assertIsNone(plugin._since(None))

    def test_the_update_note_is_honest_when_a_version_cannot_be_read(self):
        self.assertEqual(plugin._update_note('epubveri 0.13.3',
                                             'epubveri 0.13.4'),
                         'updated epubveri 0.13.3 to 0.13.4')
        self.assertEqual(plugin._update_note('', 'epubveri 0.13.4'),
                         'reinstalled epubveri 0.13.4')
        self.assertEqual(plugin._update_note('', ''), 'updated epubveri')

    def test_a_changed_binary_is_reported_and_names_the_file(self):
        """Verifying at download proves what arrived, not what runs. And the
        message has to name the file to delete: it used to say "the plugin
        folder", which after the archive fix was the wrong place."""
        tmp = tempfile.mkdtemp(prefix='epubveri-test-')
        try:
            path = os.path.join(tmp, 'epubveri')
            with open(path, 'wb') as handle:
                handle.write(b'not the binary')
            saved = dict(plugin.prefs)
            try:
                plugin.prefs['binary_sha256'] = 'a' * 64
                message = plugin._integrity_failure(path)
                self.assertIsNotNone(message)
                self.assertIn('was not run', message)
                self.assertIn(path, message)
                # A missing stored hash is an upgrade, not a failure.
                del plugin.prefs['binary_sha256']
                self.assertIsNone(plugin._integrity_failure(path))
                self.assertEqual(plugin.prefs['binary_sha256'], sha(path))
            finally:
                for key in list(plugin.prefs):
                    if key not in saved:
                        del plugin.prefs[key]
                for key, value in saved.items():
                    plugin.prefs[key] = value
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class DisplayTests(unittest.TestCase):
    def test_each_switch_hides_only_its_own_kind(self):
        """An advisory is emitted AT usage severity, so a filter written on
        severity alone would take both out together."""
        error = Finding('error')
        usage = Finding('usage')
        advisory = Finding('usage', advisory=True)
        saved = (plugin.prefs['show_usage'], plugin.prefs['show_advisory'])
        try:
            plugin.prefs['show_usage'] = True
            plugin.prefs['show_advisory'] = False
            self.assertTrue(plugin._shown(error))
            self.assertTrue(plugin._shown(usage))
            self.assertFalse(plugin._shown(advisory))

            plugin.prefs['show_usage'] = False
            plugin.prefs['show_advisory'] = True
            self.assertTrue(plugin._shown(error))
            self.assertFalse(plugin._shown(usage))
            self.assertTrue(plugin._shown(advisory))

            # Neither switch may ever hide an error.
            plugin.prefs['show_usage'] = False
            plugin.prefs['show_advisory'] = False
            self.assertTrue(plugin._shown(error))
            self.assertTrue(plugin._shown(Finding('fatal')))
            self.assertTrue(plugin._shown(Finding('warning')))
        finally:
            plugin.prefs['show_usage'], plugin.prefs['show_advisory'] = saved

    def test_every_line_says_what_it_is(self):
        self.assertEqual(plugin._label(Finding('error')), 'ERROR')
        self.assertEqual(plugin._label(Finding('usage')), 'USAGE')
        self.assertEqual(plugin._label(Finding('usage', advisory=True)),
                         'ADVISORY')


class PackagingTests(unittest.TestCase):
    """The promise the README makes: *it reads your book and reports; it
    changes nothing.* This is the test that can catch us breaking it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='epubveri-pkg-')
        self.book = build_epub(os.path.join(self.tmp, 'book.epub'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _package(self):
        from calibre.ebooks.oeb.polish.container import get_container
        container = get_container(self.book, tweak_mode=True)
        out = tempfile.mkdtemp(dir=self.tmp)
        return plugin._package(container, out)

    def test_validating_leaves_the_users_book_byte_identical(self):
        before = sha(self.book)
        self._package()
        self.assertEqual(before, sha(self.book),
                         'validating rewrote the book being edited')

    def test_nothing_in_the_packaged_book_is_re_serialised(self):
        """The whole reason `_package` is more than one call.

        Cloning stops the user's book being written to, but not the OPF being
        **re-serialised**: `EpubContainer.commit` calls
        `update_modified_timestamp()`, which dirties the OPF, and a dirtied
        file is rewritten rather than copied. calibre's serialiser is not
        byte-preserving — on this fixture it split `<dc:title>` and
        `<dc:language>` onto separate lines and wrote `<dc:creator/>` — so the
        OPF gained a line and every finding below it moved. That is the Sigil
        defect arriving by another route, and this is the test that catches it.
        """
        out = self._package()
        with zipfile.ZipFile(self.book) as a, zipfile.ZipFile(out) as b:
            produced = set(b.namelist())
            for name in a.namelist():
                self.assertIn(name, produced)
                self.assertEqual(a.read(name), b.read(name),
                                 '%s was re-serialised on the way out' % name)
            # OCF still satisfied, or every run would report a packaging error
            # the book does not have.
            self.assertEqual(b.getinfo('mimetype').compress_type,
                             zipfile.ZIP_STORED)

    def test_epubveri_says_the_same_about_the_copy_as_about_the_book(self):
        """The question Sigil answered badly for two days: are the positions
        we report positions in a document the user is looking at? Here the
        round trip must not move a single line number."""
        exe = binary()
        if exe is None:
            self.skipTest('no epubveri binary; set EPUBVERI_BINARY')

        def findings(path):
            result = subprocess.run(
                [exe, '-u', '--advisory', '--format', 'json', '-i', path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            data = json.loads(result.stdout.decode('utf-8'))['inputs'][0]
            return [(i['code'], i.get('location'),
                     (i.get('position') or {}).get('line'))
                    for i in data['items'] if i.get('type') == 'finding']

        out = self._package()
        original, copy = findings(self.book), findings(out)
        self.assertTrue(original, 'the fixture produced no findings at all')
        self.assertEqual(original, copy,
                         'the packaging moved what epubveri reports')


class DeclarationTests(unittest.TestCase):
    def test_the_settings_page_is_reachable(self):
        """Providing `config_widget` is not what opens it. Preferences /
        Plugins / Customize asks `is_customizable()` first and otherwise says
        "does not need customization" — which is what it said."""
        import calibre_plugins.epubveri as pkg
        cls = pkg.EpubVeriPlugin
        self.assertTrue(cls.is_customizable(cls))
        self.assertTrue(hasattr(cls, 'config_widget'))
        self.assertTrue(hasattr(cls, 'save_settings'))


class PackageTests(unittest.TestCase):
    """calibre's install contract is the **opposite** of Sigil's: the files
    sit at the top of the archive with no wrapping folder, and the marker file
    is what lets calibre import the package by name."""

    def test_the_archive_satisfies_calibres_install_contract(self):
        # By path, not by name: `import build` finds a different module
        # inside calibre's own environment and the test then passes or fails
        # for reasons that have nothing to do with this plugin.
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'epubveri_calibre_build', os.path.join(PLUGIN_DIR, 'build.py'))
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)

        path = build.build()
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
            self.assertIn('__init__.py', names)
            self.assertIn('main.py', names)
            self.assertIn('plugin-import-name-epubveri.txt', names)
            self.assertIn('LICENSE', names)
            self.assertIn('client/binary.py', names)
            # No wrapping folder: every entry is at the top or under a real
            # subpackage, never under a single directory named for the plugin.
            self.assertFalse([n for n in names if n.startswith('epubveri/')])
            # And never the cached binary or the tests.
            self.assertFalse([n for n in names if n.endswith('/epubveri')])
            self.assertFalse([n for n in names if n.startswith('tests/')])
        finally:
            shutil.rmtree(os.path.dirname(path), ignore_errors=True)


class ActionTests(unittest.TestCase):
    """`create_action` is called TWICE — once for the toolbar and once for the
    menu — and calibre swallows an exception from it, printing a traceback to
    stderr and carrying on (`create_plugin_action`). A plugin that throws here
    is simply absent from the menu, with nothing on screen to say so."""

    def test_it_is_built_for_both_the_toolbar_and_the_menu(self):
        tool = stub_tool()
        for for_toolbar in (True, False):
            action = tool.create_action(for_toolbar=for_toolbar)
            self.assertIsNotNone(
                action, 'calibre treats None as a failure and drops the tool')
            self.assertTrue(str(action.text()))

    def test_the_shortcut_is_registered_once_and_not_twice(self):
        """calibre's own docstring: register for only one of the toolbar
        action or the menu action, not both."""
        tool = stub_tool()
        tool.create_action(for_toolbar=True)
        tool.create_action(for_toolbar=False)
        self.assertEqual(len(tool.window.keyboard.registered), 1,
                         tool.window.keyboard.registered)
        self.assertTrue(tool.window.keyboard.registered[0].startswith(
            plugin.EpubVeriTool.name + '_'))


class ResultsDialogTests(unittest.TestCase):
    """The view has never been built by anything but a person clicking."""

    def test_every_finding_becomes_a_row_that_says_what_it_is(self):
        tool = stub_tool()
        findings = [Finding('error'),
                    Finding('usage', code='OPF-097'),
                    Finding('usage', advisory=True, code='ADV-010',
                            location='OEBPS/content.opf', line=91, column=5)]
        dialog = plugin.ResultsDialog(tool, findings, 'summary')
        self.assertEqual(dialog.items.topLevelItemCount(), 3)
        labels = [dialog.items.topLevelItem(i).text(0) for i in range(3)]
        self.assertEqual(labels, ['ERROR', 'USAGE', 'ADVISORY'])
        last = dialog.items.topLevelItem(2)
        self.assertEqual(last.text(1), 'OEBPS/content.opf')
        self.assertEqual(last.text(2), '91')
        self.assertIn('ADV-010', last.text(3))
        self.assertIn('epubcheck does not report this', last.text(3))
        # The row carries the position the editor will be sent to.
        from qt.core import Qt
        self.assertEqual(last.data(0, Qt.ItemDataRole.UserRole),
                         ('OEBPS/content.opf', 91, 5))

    def test_a_clean_book_still_opens_a_window(self):
        """Zero findings is the commonest happy case and the easiest one to
        build a view that crashes on."""
        tool = stub_tool()
        dialog = plugin.ResultsDialog(tool, [], 'epubveri — VALID')
        self.assertEqual(dialog.items.topLevelItemCount(), 0)
        self.assertIn('VALID', dialog.summary.text())

    def test_a_finding_with_no_file_neither_crashes_nor_navigates(self):
        """Container-level findings carry no location. Activating one must do
        nothing rather than raise inside Qt's event handler."""
        tool = stub_tool()
        dialog = plugin.ResultsDialog(
            tool, [Finding('error', location=None, line=None, column=None)],
            'summary')
        item = dialog.items.topLevelItem(0)
        self.assertEqual(item.text(1), '')
        self.assertEqual(item.text(2), '')
        self.assertIsNone(dialog.go_to(item))


class Envelope(object):
    """Enough of an envelope for the summary line."""

    def __init__(self, findings, version='0.13.3'):
        self.findings = findings
        self.version = version
        self.could_not_read = False
        self.error = None

    @property
    def is_valid(self):
        return not [f for f in self.findings
                    if f.severity in ('error', 'fatal')]

    def count(self, severity):
        return len([f for f in self.findings if f.severity == severity])


class SummaryTests(unittest.TestCase):
    """The arithmetic, which is the easy thing to get quietly wrong: an
    advisory is emitted AT usage severity, so a naive count reports it twice.
    """

    def _summary(self, findings):
        tool = stub_tool()
        tool._show(Envelope(findings), None)
        return tool._results.summary.text()

    def test_advisories_are_not_counted_as_usage_notes_as_well(self):
        findings = [Finding('usage'), Finding('usage'),
                    Finding('usage', advisory=True)]
        text = self._summary(findings)
        self.assertIn('2 usage note(s)', text)
        self.assertIn('1 advisory finding(s)', text)
        self.assertNotIn('3 usage note(s)', text)

    def test_only_errors_and_warnings_decide_the_verdict(self):
        text = self._summary([Finding('usage'), Finding('usage', advisory=True)])
        self.assertIn('VALID', text)
        self.assertNotIn('NOT VALID', text)
        self.assertIn('0 error(s)', text)
        self.assertIn('neither affects the verdict', text)

        text = self._summary([Finding('fatal'), Finding('error'),
                              Finding('warning')])
        self.assertIn('NOT VALID', text)
        self.assertIn('2 error(s)', text)      # a fatal counts as an error
        self.assertIn('1 warning(s)', text)

    def test_a_hidden_finding_is_declared_never_silently_dropped(self):
        """A shorter report with no explanation is the one thing a display
        switch must not produce."""
        saved = plugin.prefs['show_advisory']
        try:
            plugin.prefs['show_advisory'] = False
            text = self._summary([Finding('error'),
                                  Finding('usage', advisory=True)])
            self.assertIn('1 finding(s) are not listed', text)
            self.assertIn('Customize', text)
        finally:
            plugin.prefs['show_advisory'] = saved

    def test_validating_twice_replaces_the_window_rather_than_stacking(self):
        """The dialog is non-modal, so nothing stops them accumulating — and
        an old one reports a book that has since been edited."""
        tool = stub_tool()
        tool._show(Envelope([Finding('error')]), None)
        first = tool._results
        tool._show(Envelope([Finding('usage')]), None)
        self.assertIsNot(tool._results, first)
        self.assertFalse(first.isVisible())
        self.assertIn('1 usage note(s)', tool._results.summary.text())

    def test_nothing_is_said_about_settings_when_nothing_is_hidden(self):
        text = self._summary([Finding('error')])
        self.assertNotIn('not listed', text)


class ConfigWidgetTests(unittest.TestCase):
    def test_the_three_switches_show_and_save(self):
        qt_app()
        saved = {k: plugin.prefs[k]
                 for k in ('autoupdate', 'show_usage', 'show_advisory')}
        try:
            for key in saved:
                plugin.prefs[key] = True
            widget = plugin.ConfigWidget()
            from qt.core import QCheckBox
            boxes = widget.findChildren(QCheckBox)
            self.assertEqual(len(boxes), 3)
            self.assertTrue(all(b.isChecked() for b in boxes),
                            'the defaults must match the Sigil plugin')

            widget.show_usage.setChecked(False)
            widget.save_settings()
            self.assertFalse(plugin.prefs['show_usage'])
            self.assertTrue(plugin.prefs['autoupdate'])
            # and a freshly built page shows what was saved. The widget has
            # to be held: unreferenced, Qt deletes it and reading a child
            # raises "wrapped C/C++ object has been deleted".
            reopened = plugin.ConfigWidget()
            self.assertFalse(reopened.show_usage.isChecked())
            self.assertTrue(reopened.check_updates.isChecked())
        finally:
            for key, value in saved.items():
                plugin.prefs[key] = value


def run():
    """`unittest.main()` finds nothing here.

    `calibre-debug script.py` executes the file in a fresh globals dict rather
    than as `sys.modules['__main__']`, so unittest's default discovery looks
    at calibre's own `__main__` and sees no tests — and reports "NO TESTS RAN"
    rather than an error, which is the sort of green that means nothing. The
    suite is therefore built from this module's own namespace.
    """
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    cases = [obj for obj in globals().values()
             if isinstance(obj, type) and issubclass(obj, unittest.TestCase)]
    for case in cases:
        suite.addTests(loader.loadTestsFromTestCase(case))
    if not suite.countTestCases():
        raise SystemExit('no tests were collected — the suite is not running')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    run()
