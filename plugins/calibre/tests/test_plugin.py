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
_sub.__file__ = os.path.join(PLUGIN_DIR, '__init__.py')
sys.modules['calibre_plugins.epubveri'] = _sub
# And run the real `__init__.py` into it. An empty stand-in is not the package
# calibre builds: it has no PLUGIN_VERSION, which `main` names in the summary
# line, so a module-level import of it passed inside calibre and failed here.
# A harness that differs from production in what it *defines* will keep
# producing that shape of failure.
with open(_sub.__file__, encoding='utf-8') as _handle:
    exec(compile(_handle.read(), _sub.__file__, 'exec'), _sub.__dict__)

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


def Qt_sort_order_descending():
    from qt.core import Qt
    return Qt.SortOrder.DescendingOrder


def Qt_sort_order_ascending():
    from qt.core import Qt
    return Qt.SortOrder.AscendingOrder


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
    # A QMainWindow, not a bare QWidget: `Tool.gui` is `tweak_book.ui.Main`,
    # whose MRO is Main -> MainWindow -> QMainWindow, and the results dock is
    # added to it. A stub that cannot hold a dock is a stub that tests
    # something production never does.
    from qt.core import QMainWindow
    qt_app()
    window = QMainWindow()
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
            os.path.normpath(os.path.join(config_dir, 'plugins',
                                          'epubveri-data')))
        self.assertNotEqual(os.path.normpath(plugin._data_dir()),
                            os.path.normpath(PLUGIN_DIR))

    def test_it_is_not_the_name_the_other_plugin_already_uses(self):
        """`<config>/plugins/epubveri` is a **file** in Doitsu's calibre
        plugin — his binary, `epubveri_plugin_dir()` + `epubveri_binary_name()`
        in his 0.0.7 — on every platform but Windows. A folder of ours with
        that name breaks his plugin as surely as his file broke ours."""
        from calibre.constants import config_dir
        self.assertNotEqual(
            os.path.normpath(plugin._data_dir()),
            os.path.normpath(os.path.join(config_dir, 'plugins', 'epubveri')))

    def test_a_folder_left_by_0_2_0_is_moved_rather_than_abandoned(self):
        """0.2.0 kept the binary under the shared name. The move gives this
        plugin the copy it already verified **and** hands the name back to the
        plugin that owns it, which is the half that is easy to forget: his
        code cannot run while a directory sits where his file goes."""
        base = tempfile.mkdtemp(prefix='epubveri-datadir-')
        try:
            legacy = os.path.join(base, 'epubveri')
            new = os.path.join(base, 'epubveri-data')
            os.makedirs(legacy)
            binary = os.path.join(legacy, plugin.bin_mod.binary_filename())
            with open(binary, 'w', encoding='utf-8') as handle:
                handle.write('pretend this is 2.8 MB of validator')

            self.assertEqual(plugin._prepare_data_dir(new, legacy=legacy), new)
            self.assertTrue(os.path.isfile(
                os.path.join(new, plugin.bin_mod.binary_filename())))
            self.assertFalse(os.path.lexists(legacy),
                             "the shared name is still taken, so his plugin "
                             "is still broken")
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_the_other_plugins_binary_is_never_touched(self):
        """The migration moves a **folder of ours**. His `epubveri` is a
        file, and a file at that path is his: it is left exactly where it
        is, and it does not stop us starting fresh under our own name."""
        base = tempfile.mkdtemp(prefix='epubveri-datadir-')
        try:
            his = os.path.join(base, 'epubveri')
            new = os.path.join(base, 'epubveri-data')
            with open(his, 'w', encoding='utf-8') as handle:
                handle.write('his binary')

            self.assertEqual(plugin._prepare_data_dir(new, legacy=his), new)
            self.assertTrue(os.path.isdir(new))
            self.assertTrue(os.path.isfile(his))
            with open(his, encoding='utf-8') as handle:
                self.assertEqual(handle.read(), 'his binary')
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_a_folder_that_is_not_ours_is_left_where_it_is(self):
        """Only a folder holding our binary is recognised as ours. Anything
        else at that name is someone's data, and moving it would be a bug
        with no way back."""
        base = tempfile.mkdtemp(prefix='epubveri-datadir-')
        try:
            legacy = os.path.join(base, 'epubveri')
            new = os.path.join(base, 'epubveri-data')
            os.makedirs(legacy)
            with open(os.path.join(legacy, 'notes.txt'), 'w',
                      encoding='utf-8') as handle:
                handle.write('somebody else')

            self.assertEqual(plugin._prepare_data_dir(new, legacy=legacy), new)
            self.assertTrue(os.path.isfile(os.path.join(legacy, 'notes.txt')))
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_a_name_in_the_way_is_reported_instead_of_the_network(self):
        """PeterT's first run on Linux (MobileRead 374940 #19) said the
        binary "could not be downloaded" and that the first run "needs an
        internet connection", with `[Errno 17] File exists` in brackets. His
        connection was fine: something was already sitting at this path.

        Two shapes of that, and `os.path.isdir` is False for both: a plain
        file, and a symlink whose target is gone. Neither may reach the
        network sentence.
        """
        for make in ('file', 'dead symlink'):
            base = tempfile.mkdtemp(prefix='epubveri-datadir-')
            try:
                path = os.path.join(base, 'epubveri')
                if make == 'file':
                    with open(path, 'w', encoding='utf-8') as handle:
                        handle.write('not a folder')
                else:
                    os.symlink(os.path.join(base, 'gone'), path)
                self.assertFalse(os.path.isdir(path), make)

                with self.assertRaises(plugin.InstallPathError, msg=make):
                    plugin._prepare_data_dir(path)
                try:
                    plugin._prepare_data_dir(path)
                except plugin.InstallPathError as exc:
                    said = plugin._install_failure(exc)
                self.assertIn(path, said, make)
                self.assertNotIn('internet connection', said, make)
                # And the thing in the way is still there: this reports, it
                # does not tidy up after the user.
                self.assertTrue(os.path.exists(path) or os.path.islink(path))
            finally:
                shutil.rmtree(base, ignore_errors=True)

    def test_a_folder_that_is_already_there_is_simply_used(self):
        """The ordinary case, and the second call is the one that matters:
        two editor windows opening together must not turn `exist_ok` into a
        second, unrelated version of the message above."""
        base = tempfile.mkdtemp(prefix='epubveri-datadir-')
        try:
            path = os.path.join(base, 'epubveri')
            self.assertEqual(plugin._prepare_data_dir(path), path)
            self.assertEqual(plugin._prepare_data_dir(path), path)
            self.assertTrue(os.path.isdir(path))
        finally:
            shutil.rmtree(base, ignore_errors=True)


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

    def test_the_time_of_a_check_is_written_the_way_his_plugin_reads_it(self):
        """calibre keys preferences by the plugin **name**, and Doitsu's
        calibre plugin is also called `epubveri`, so both plugins share one
        `plugins/epubveri.json`. `last_update_check` is his key first: he
        writes `time.time()` and computes `time.time() - last_checked`.

        Up to 0.2.0 we wrote an ISO string into it, which made that
        subtraction raise `TypeError` for anyone who ran ours and then his.
        Our own reader was tolerant, so the breakage was one-way and it was
        not ours to notice — which is the argument for writing his spelling
        rather than defending our own.
        """
        import time
        stamp = plugin._stamp()
        self.assertIsInstance(stamp, float)
        # His arithmetic, run against our value.
        self.assertLess(abs(time.time() - stamp), 60)
        # And the control: the value 0.2.0 wrote is what broke it.
        with self.assertRaises(TypeError):
            time.time() - plugin._now().isoformat()

    def test_both_spellings_of_a_stamp_are_read(self):
        """The epoch seconds written now, and the ISO strings already sitting
        in every 0.2.0 install. A format change is not a reason to make every
        existing install think it has never checked."""
        from datetime import timedelta
        recent = plugin._now() - timedelta(minutes=5)
        for value in (recent.timestamp(), recent.isoformat()):
            age = plugin._since(value)
            self.assertIsNotNone(age, value)
            self.assertLess(age, timedelta(hours=1), value)
        self.assertIsNone(plugin._since(0))
        self.assertIsNone(plugin._since(float('nan')))

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

        # **Built into a temp directory, and this is not tidiness.** `build()`
        # writes to `dist/<editor>/`, and the cleanup below used to be
        # `rmtree(os.path.dirname(path))` — so running the tests after a build
        # deleted the archive that had just been built, and `dist/` emptying
        # itself went unexplained for days. `DIST` is read inside `build()`,
        # so pointing it somewhere disposable is enough.
        outdir = tempfile.mkdtemp(prefix='epubveri-build-')
        build.DIST = outdir
        path = build.build()
        try:
            self.assertTrue(
                os.path.abspath(path).startswith(os.path.abspath(outdir)),
                "the build ignored DIST, so this test is about to delete a "
                "real dist/ directory: %s" % path)
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
            shutil.rmtree(outdir, ignore_errors=True)


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


class ResultsPanelTests(unittest.TestCase):
    """The view has never been built by anything but a person clicking."""

    def _panel(self, findings, summary='summary', base=None):
        tool = stub_tool()
        panel = plugin.ResultsPanel(tool)
        if base is not None:
            # The theme is read off the widget's own palette, so a test that
            # wants a theme sets one rather than hoping the machine running
            # it has the right one.
            from qt.core import QPalette, QColor
            palette = QPalette(panel.palette())
            palette.setColor(QPalette.ColorRole.Base, QColor(base))
            panel.setPalette(palette)
        panel.show_results(findings, summary)
        return panel

    def _backgrounds(self, panel):
        return [panel.items.topLevelItem(i).background(0).color().getRgb()[:3]
                for i in range(panel.items.topLevelItemCount())]

    def test_a_row_is_tinted_by_the_word_in_its_first_column(self):
        """thiago.eec asked for the line colours he had in Doitsu's plugin
        (MobileRead 374940 #20) and Doitsu posted the set (#21). Fatal and
        error share a colour there and share one here."""
        panel = self._panel([Finding('fatal'), Finding('error'),
                             Finding('warning'), Finding('info'),
                             Finding('usage'),
                             Finding('usage', advisory=True)],
                            base='#ffffff')
        self.assertEqual(self._backgrounds(panel), [
            (255, 230, 230), (255, 230, 230), (255, 255, 230),
            (224, 255, 255), (224, 255, 255), (224, 255, 255)])
        # Every column, not just the first: a row that is half tinted reads
        # as a rendering fault.
        row = panel.items.topLevelItem(0)
        for column in range(panel.items.columnCount()):
            self.assertEqual(row.background(column).color().getRgb()[:3],
                             (255, 230, 230), column)

    def test_the_light_set_is_the_one_he_posted_to_the_byte(self):
        """Pinned rather than described. thiago is asking for the colours he
        already knows; drifting from them by a shade would answer a request
        nobody made, and the two plugins sitting side by side would look
        almost-but-not-quite alike."""
        self.assertEqual(plugin._TINTS_LIGHT['FATAL'], (255, 230, 230))
        self.assertEqual(plugin._TINTS_LIGHT['ERROR'], (255, 230, 230))
        self.assertEqual(plugin._TINTS_LIGHT['WARNING'], (255, 255, 230))
        self.assertEqual(plugin._TINTS_LIGHT['INFO'], (224, 255, 255))
        self.assertEqual(plugin._TINTS_LIGHT['USAGE'], (224, 255, 255))

    def test_a_dark_theme_gets_dark_rows_and_keeps_its_own_text(self):
        """His plugin paints the pale rows in both themes and forces the text
        black on top of them — which is what made it readable in the dark and
        what makes a dark editor grow bright bands. The tint follows the theme
        here instead, and **no foreground is set at all**, so the text stays
        the colour the user's theme chose."""
        from qt.core import Qt
        panel = self._panel([Finding('error'), Finding('warning'),
                             Finding('usage')], base='#1e1e1e')
        for red, green, blue in self._backgrounds(panel):
            luminance = 0.299 * red + 0.587 * green + 0.114 * blue
            self.assertLess(luminance, 128, (red, green, blue))
        for index in range(3):
            self.assertIsNone(
                panel.items.topLevelItem(index).data(
                    0, Qt.ItemDataRole.ForegroundRole),
                "a foreground was forced, so the theme no longer decides")

    def _labels(self, panel):
        return [panel.items.topLevelItem(i).text(0)
                for i in range(panel.items.topLevelItemCount())]

    def _sorted_panel(self, findings, order='severity'):
        saved = plugin.prefs['sort']
        try:
            plugin.prefs['sort'] = order
            return self._panel(findings)
        finally:
            plugin.prefs['sort'] = saved

    def test_the_panel_opens_severest_first(self):
        """The words sort alphabetically as ERROR < FATAL < INFO < USAGE <
        WARNING, so a table left to Qt puts a fatal below an error. Severity
        is the default because it is what epubveri's own CLI shows a person
        and what calibre's Check Book does."""
        panel = self._sorted_panel([Finding('usage'), Finding('info'),
                                    Finding('error'), Finding('fatal'),
                                    Finding('usage', advisory=True),
                                    Finding('warning')])
        self.assertEqual(self._labels(panel),
                         ['FATAL', 'ERROR', 'WARNING', 'INFO', 'USAGE',
                          'ADVISORY'])

    def test_inside_one_severity_the_book_order_is_kept(self):
        """What `--sort severity` does in the CLI: group by severity, and
        leave each group reading top-to-bottom. A sort that shuffled a group
        would make the panel harder to work through, not easier."""
        panel = self._sorted_panel([
            Finding('error', location='c.xhtml', line=3),
            Finding('usage', location='a.xhtml', line=1),
            Finding('error', location='a.xhtml', line=9),
            Finding('error', location='b.xhtml', line=1)])
        rows = [(panel.items.topLevelItem(i).text(0),
                 panel.items.topLevelItem(i).text(1))
                for i in range(4)]
        self.assertEqual(rows, [('ERROR', 'c.xhtml'), ('ERROR', 'a.xhtml'),
                                ('ERROR', 'b.xhtml'), ('USAGE', 'a.xhtml')])

    def test_least_severe_first_is_the_same_table_reversed(self):
        panel = self._sorted_panel([Finding('usage'), Finding('fatal'),
                                    Finding('warning')],
                                   order='severity-low')
        self.assertEqual(self._labels(panel), ['USAGE', 'WARNING', 'FATAL'])

    def test_the_line_column_counts_rather_than_spells(self):
        """9 before 10, which is not what a table of strings does. Sigil's own
        results table has this the other way round — it builds the cell with
        `QTableWidgetItem(QString::number(line))` — and so does any plugin
        that hands Qt plain text."""
        panel = self._sorted_panel([Finding('error', line=9),
                                    Finding('error', line=10),
                                    Finding('error', line=100),
                                    Finding('error', line=None)])
        # What a click ends up doing. `sectionClicked` is only the wiring
        # for the first click in document order; QHeaderView sorts through
        # its own internal handling, which `emit` does not reach.
        panel.items.sortItems(plugin.COL_LINE, Qt_sort_order_ascending())
        self.assertEqual(
            [panel.items.topLevelItem(i).text(2) for i in range(4)],
            ['', '9', '10', '100'])

    def test_document_order_is_left_alone_until_a_header_is_clicked(self):
        """Qt has no unsorted state once sorting is on, so `document` is
        offered by not sorting at all — and clicking a header has to still
        work, or choosing that order would cost the user the feature."""
        findings = [Finding('usage'), Finding('fatal'), Finding('warning')]
        panel = self._sorted_panel(findings, order='document')
        self.assertEqual(self._labels(panel), ['USAGE', 'FATAL', 'WARNING'])
        self.assertFalse(panel.items.isSortingEnabled())

        panel.items.header().sectionClicked.emit(plugin.COL_SEVERITY)
        self.assertEqual(self._labels(panel), ['FATAL', 'WARNING', 'USAGE'])

    def test_a_header_click_is_not_undone_by_validating_again(self):
        """The setting says how the panel opens, once. After that the user's
        click owns the order for the session — otherwise every validation
        would quietly put it back."""
        panel = self._sorted_panel([Finding('fatal'), Finding('usage')])
        self.assertEqual(self._labels(panel), ['FATAL', 'USAGE'])
        # The user clicks Severity a second time, reversing it.
        panel.items.sortItems(plugin.COL_SEVERITY,
                              Qt_sort_order_descending())
        panel.show_results([Finding('fatal'), Finding('usage')], 'again')
        self.assertEqual(self._labels(panel), ['USAGE', 'FATAL'])

    def test_a_severity_we_do_not_know_sorts_last_not_among_the_errors(self):
        panel = self._sorted_panel([Finding('mystery'), Finding('usage'),
                                    Finding('error')])
        self.assertEqual(self._labels(panel), ['ERROR', 'USAGE', 'MYSTERY'])

    def test_a_severity_we_do_not_know_is_left_untinted(self):
        """A word this table has never seen should look unremarkable rather
        than be filed under one of the three families by a default."""
        from qt.core import Qt
        panel = self._panel([Finding('mystery')], base='#ffffff')
        self.assertIsNone(panel.items.topLevelItem(0).data(
            0, Qt.ItemDataRole.BackgroundRole))

    def test_every_finding_becomes_a_row_that_says_what_it_is(self):
        panel = self._panel([
            Finding('error'),
            Finding('usage', code='OPF-097'),
            Finding('usage', advisory=True, code='ADV-010',
                    location='OEBPS/content.opf', line=91, column=5)])
        self.assertEqual(panel.items.topLevelItemCount(), 3)
        labels = [panel.items.topLevelItem(i).text(0) for i in range(3)]
        self.assertEqual(labels, ['ERROR', 'USAGE', 'ADVISORY'])
        last = panel.items.topLevelItem(2)
        self.assertEqual(last.text(1), 'OEBPS/content.opf')
        self.assertEqual(last.text(2), '91')
        self.assertIn('ADV-010', last.text(3))
        self.assertIn('epubcheck does not report this', last.text(3))
        # The row carries the position the editor will be sent to.
        from qt.core import Qt
        self.assertEqual(last.data(0, Qt.ItemDataRole.UserRole),
                         ('OEBPS/content.opf', 91, 5))

    def test_a_clean_book_still_fills_the_panel(self):
        """Zero findings is the commonest happy case and the easiest one to
        build a view that crashes on."""
        panel = self._panel([], 'epubveri — VALID')
        self.assertEqual(panel.items.topLevelItemCount(), 0)
        self.assertIn('VALID', panel.summary.text())

    def test_showing_again_replaces_the_rows_rather_than_appending(self):
        """The panel is reused, so nothing else clears it."""
        panel = self._panel([Finding('error'), Finding('error')], 'first')
        self.assertEqual(panel.items.topLevelItemCount(), 2)
        panel.show_results([Finding('usage')], 'second')
        self.assertEqual(panel.items.topLevelItemCount(), 1)
        self.assertEqual(panel.summary.text(), 'second')

    def test_a_finding_with_no_file_neither_crashes_nor_navigates(self):
        """Container-level findings carry no location. Activating one must do
        nothing rather than raise inside Qt's event handler."""
        panel = self._panel(
            [Finding('error', location=None, line=None, column=None)])
        item = panel.items.topLevelItem(0)
        self.assertEqual(item.text(1), '')
        self.assertEqual(item.text(2), '')
        self.assertIsNone(panel.go_to(item))


class ResultsDockTests(unittest.TestCase):
    """Doitsu asked for a dock rather than a window (MobileRead 374940 #16);
    JSWolf said that was more than a nitpick (#17)."""

    def test_the_dock_is_built_once_though_create_action_is_called_twice(self):
        """calibre calls `create_action` for the toolbar and again for the
        menu, on one instance. It also swallows an exception from it — the
        traceback goes to stderr and the tool vanishes from the menu with
        nothing on screen — so a second dock here would be close to
        invisible."""
        tool = stub_tool()
        tool.create_action(for_toolbar=True)
        tool.create_action(for_toolbar=False)
        from qt.core import QDockWidget
        docks = tool.window.findChildren(QDockWidget)
        self.assertEqual(len(docks), 1, docks)
        self.assertIs(docks[0], tool._dock)

    def test_the_action_takes_the_icon_calibre_hands_it(self):
        """calibre's own idiom is `QAction(get_icons('myicon.png'), ...)`, and
        this plugin shipped without one — the toolbar and the Plugins menu had
        text and nothing else.

        `get_icons` is injected into the module by calibre's zip loader, so
        under the tests it does not exist. Inject one and check the action
        actually asked for the file that `build.py` puts at the archive root.
        """
        asked = []

        def fake_get_icons(name):
            from qt.core import QIcon
            asked.append(name)
            return QIcon()

        plugin.__dict__['get_icons'] = fake_get_icons
        try:
            tool = stub_tool()
            tool.create_action()
        finally:
            del plugin.__dict__['get_icons']
        self.assertEqual(asked, ['plugin.png'])

    def test_no_zip_means_no_icon_and_no_exception(self):
        """Calling `get_icons` blind would raise NameError inside
        `create_action`, and calibre swallows that: `create_plugin_action`
        prints a traceback to stderr and drops the tool from the menu with
        nothing on screen. So the tool must load with no injection at all."""
        self.assertNotIn('get_icons', plugin.__dict__)
        tool = stub_tool()
        action = tool.create_action()
        self.assertIsNotNone(action)
        self.assertTrue(action.icon().isNull())

    def test_the_shipped_icon_is_the_one_icon_py_draws(self):
        """The same three-copies problem the Sigil side has: one mark, two
        plugins, and nothing but this notices when they stop agreeing."""
        import importlib.util
        root = os.path.dirname(os.path.dirname(PLUGIN_DIR))
        spec = importlib.util.spec_from_file_location(
            'epubveri_icon', os.path.join(root, 'icon.py'))
        icon = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(icon)

        import tempfile
        fd, path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        try:
            icon.write_png(path, 128)
            with open(path, 'rb') as a, \
                    open(os.path.join(PLUGIN_DIR, 'plugin.png'), 'rb') as b:
                self.assertEqual(a.read(), b.read(),
                                 'plugin.png does not match the geometry; '
                                 'run icon.py')
        finally:
            os.unlink(path)

    def test_the_dock_carries_the_name_calibre_saves_its_position_under(self):
        """calibre's own docks set an objectName with the comment "Needed for
        saveState". Without one Qt cannot restore where the user put it."""
        tool = stub_tool()
        tool.create_action()
        self.assertEqual(tool._dock.objectName(), tool.DOCK_OBJECT_NAME)
        # And the literal, on purpose. This name is persisted in the user's
        # saved window layout, so renaming it in a later version silently
        # orphans wherever they had put the panel — the same shape as a
        # preference key outliving the feature that wrote it, which cost a
        # real user a silently-hidden category. A test that has to be edited
        # is the cheapest way to make that a decision instead of an accident.
        self.assertEqual(tool.DOCK_OBJECT_NAME, 'epubveri-results-dock')

    def test_it_starts_hidden_and_a_validation_brings_it_up(self):
        """Nothing should appear until the user asks for a validation, which
        is how calibre brings up Live CSS."""
        tool = stub_tool()
        tool.create_action()
        self.assertFalse(tool._dock.isVisibleTo(tool.window))
        tool._show(Envelope([Finding('error')]), None)
        self.assertTrue(tool._dock.isVisibleTo(tool.window))

    def test_calibre_remembers_where_the_dock_was_put(self):
        """The claim the whole `create_action` timing exists to earn, done as
        a round trip rather than asserted.

        `Main.__init__` runs `create_actions()` — where this dock is built —
        before `create_docks()`, and defers `restore_state` to
        `QTimer.singleShot(0, ...)`, so the dock exists by the time
        `restoreState` runs. Nothing of ours is stored anywhere; if this is
        wrong the panel returns to the default corner every session and the
        only way to find out is to use calibre for a week.

        Move it, save the window state, build a fresh window and dock the way
        a new session would, restore, and see where it lands.
        """
        from qt.core import Qt
        version = 0

        first = stub_tool()
        first.create_action()
        self.assertEqual(first.window.dockWidgetArea(first._dock),
                         Qt.DockWidgetArea.TopDockWidgetArea)
        # The user drags it to the bottom and leaves it open.
        first.window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,
                                   first._dock)
        first._dock.show()
        state = bytes(first.window.saveState(version))
        self.assertTrue(state)

        second = stub_tool()
        second.create_action()
        self.assertTrue(second.window.restoreState(state, version))
        self.assertEqual(second.window.dockWidgetArea(second._dock),
                         Qt.DockWidgetArea.BottomDockWidgetArea,
                         "the dock did not come back where it was put")
        self.assertTrue(second._dock.isVisibleTo(second.window),
                        "it came back but closed")

    def test_without_the_object_name_nothing_is_remembered(self):
        """The control that makes the test above mean something. Qt matches a
        saved dock to a live one by objectName and by nothing else, which is
        why calibre's own docks set one with the comment "Needed for
        saveState"."""
        from qt.core import Qt
        version = 0

        first = stub_tool()
        first.create_action()
        first.window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,
                                   first._dock)
        first._dock.show()
        state = bytes(first.window.saveState(version))

        nameless = stub_tool()
        nameless.create_action()
        nameless._dock.setObjectName('')
        nameless.window.restoreState(state, version)
        self.assertEqual(nameless.window.dockWidgetArea(nameless._dock),
                         Qt.DockWidgetArea.TopDockWidgetArea,
                         "a nameless dock was matched, so this test proves "
                         "nothing about the named one")

    def test_a_session_that_ended_open_starts_closed(self):
        """thiago.eec asked for this and Doitsu agreed (MobileRead 374940
        #20, #21): the panel should not be on screen at startup, the way the
        EPUBCheck and ACE plugins are not. Those are dialogs and get it for
        free; `restoreState` restores a dock's **visibility** as well as its
        position, so ours has to be closed again afterwards.

        Production's ordering is reproduced rather than described:
        `create_action` runs first and queues our deferred close, calibre
        queues `restore_state` after it, and only then does an event loop
        turn. What must survive is the position — dropping that to win this
        would be trading one request for another.
        """
        from qt.core import Qt, QTimer
        version = 0

        first = stub_tool()
        first.create_action()
        first.window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,
                                   first._dock)
        first._dock.show()
        state = bytes(first.window.saveState(version))

        second = stub_tool()
        second.create_action()
        # calibre: `QTimer.singleShot(0, self.restore_state)`, at the end of
        # `Main.__init__` — after `create_actions()`, which is the ordering
        # the deferred close depends on.
        QTimer.singleShot(0, lambda: second.window.restoreState(state,
                                                               version))
        for _ in range(10):
            qt_app().processEvents()

        self.assertEqual(second.window.dockWidgetArea(second._dock),
                         Qt.DockWidgetArea.BottomDockWidgetArea,
                         "the position stopped being remembered")
        self.assertFalse(second._dock.isVisibleTo(second.window),
                         "the panel came back on screen with nothing in it")

    def test_a_panel_with_findings_in_it_is_never_closed_underneath(self):
        """The control for the test above. The deferred close is timing, and
        timing is the kind of thing a future calibre can reorder; whatever it
        does, it may not take away a panel someone is reading."""
        tool = stub_tool()
        tool.create_action()
        tool._show(Envelope([Finding('error')]), None)
        for _ in range(10):
            qt_app().processEvents()
        self.assertTrue(tool._dock.isVisibleTo(tool.window))

    def test_validating_twice_reuses_the_one_dock(self):
        """The dialog this replaces had to close its predecessor by hand, or
        three validations left three windows and two of them described a book
        that had since been edited."""
        tool = stub_tool()
        tool._show(Envelope([Finding('error')]), None)
        first = tool._dock
        tool._show(Envelope([Finding('usage')]), None)
        self.assertIs(tool._dock, first)
        from qt.core import QDockWidget
        self.assertEqual(len(tool.window.findChildren(QDockWidget)), 1)
        self.assertIn('1 usage note(s)', tool._panel.summary.text())


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
        return tool._panel.summary.text()

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

    def test_the_summary_names_the_plugin_version_beside_epubveri_s(self):
        """Doitsu, MobileRead 374939 #21: "add the plugin version number for
        debugging purposes". Two versions because two things can be wrong, and
        most of what has gone wrong in these plugins was the plugin.

        It comes from the tuple calibre itself reads, so there is no second
        copy that can disagree with what Preferences shows.
        """
        from calibre_plugins.epubveri import (PLUGIN_VERSION,
                                              PLUGIN_VERSION_TUPLE)
        text = self._summary([Finding('error')])
        self.assertIn('(plugin %s)' % PLUGIN_VERSION, text)
        self.assertEqual(PLUGIN_VERSION,
                         '.'.join(str(p) for p in PLUGIN_VERSION_TUPLE))

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

    def test_nothing_is_said_about_settings_when_nothing_is_hidden(self):
        text = self._summary([Finding('error')])
        self.assertNotIn('not listed', text)


class ConfigWidgetTests(unittest.TestCase):
    """**These build the page under Fusion rather than calibre's own style,
    and the reason is a real crash.** With `CalibreStyle` active, building a
    page containing a `QComboBox` here dies with SIGBUS inside
    `CalibreStyle::standardIcon`, which asks the application object for an
    icon through `QMetaObject::invokeMethod` — a round trip that wants more
    of a calibre than `Application([])` is in a test process. calibre's own
    preference pages are full of combo boxes, so this is the harness and not
    the widget; the page is still worth building under a plain style, because
    what these tests are about is which settings it shows and saves.
    """

    def setUp(self):
        qt_app().setStyle('Fusion')

    def test_the_three_switches_show_and_save(self):
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

    def test_the_sort_box_offers_epubveris_own_words_and_defaults_to_severity(
            self):
        """The values are `--sort`'s, so the CLI, this plugin and the Sigil
        one can all be asked the same question in the same words. Severity is
        the default: it is what the CLI shows a person, and what calibre's own
        Check Book does."""
        saved = plugin.prefs['sort']
        try:
            plugin.prefs['sort'] = 'severity'
            widget = plugin.ConfigWidget()
            values = [widget.sort.itemData(i)
                      for i in range(widget.sort.count())]
            self.assertEqual(values, list(plugin.SORT_ORDERS))
            self.assertEqual(widget.sort.currentData(), 'severity')

            widget.sort.setCurrentIndex(values.index('document'))
            widget.save_settings()
            self.assertEqual(plugin.prefs['sort'], 'document')
            reopened = plugin.ConfigWidget()
            self.assertEqual(reopened.sort.currentData(), 'document')
        finally:
            plugin.prefs['sort'] = saved

    def test_a_settings_file_with_a_word_we_do_not_know_still_opens(self):
        """Hand-edited files are a supported way to set these — DNSB says he
        edits the Sigil plugin's JSON rather than using a dialog. A typo must
        land on the default rather than on an empty box."""
        saved = plugin.prefs['sort']
        try:
            plugin.prefs['sort'] = 'sevrity'
            widget = plugin.ConfigWidget()
            self.assertEqual(widget.sort.currentData(), 'severity')
        finally:
            plugin.prefs['sort'] = saved


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
