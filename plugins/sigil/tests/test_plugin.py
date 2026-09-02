# epubveri for Sigil — tests
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Drive `plugin.run(bk)` against a fake Sigil container.

Sigil cannot be scripted, so the parts that can go wrong silently are pinned
here instead: that the temporary `.epub` we hand epubveri is a *valid
container* (mimetype first and stored — get that wrong and every run reports a
packaging error the book does not have), that a full container-relative path
reaches `add_result` rather than a basename, and that the display filters do
what their names say.

Set EPUBVERI_BINARY to test against a build other than the installed one.
"""

import os
import sys
import unittest
import zipfile

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)

import plugin  # noqa: E402


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
       '<head><title>t</title></head><body><p>x</p></body></html>')
CONTAINER = ('<?xml version="1.0"?>\n<container version="1.0" '
             'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
             '<rootfile full-path="OEBPS/content.opf" '
             'media-type="application/oebps-package+xml"/></rootfiles></container>')

FILES = {
    "mimetype": "application/epub+zip",
    "META-INF/container.xml": CONTAINER,
    "OEBPS/content.opf": OPF,
    "OEBPS/nav.xhtml": NAV,
    "OEBPS/Text/ch1.xhtml": CH1,
    "OEBPS/Misc/spare.xml": "<r/>",
}


class FakeBk(object):
    """The four container methods the plugin uses, and nothing else."""

    def __init__(self, prefs=None):
        self.prefs = dict(prefs or {})
        self.results = []

    def getPrefs(self):
        return self.prefs

    def savePrefs(self, prefs):
        self.prefs = prefs

    def get_opfbookpath(self):
        return "OEBPS/content.opf"

    def get_opf(self):
        return OPF

    def copy_book_contents_to(self, destdir):
        for name, text in FILES.items():
            path = os.path.join(destdir, name.replace("/", os.sep))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)

    def add_result(self, restype, bookpath, linenumber, message):
        self.results.append((restype, bookpath, linenumber, -1, message))

    def add_extended_result(self, restype, bookpath, linenumber, charoffset,
                            message):
        self.results.append((restype, bookpath, linenumber, charoffset,
                             message))


def _binary():
    path = os.environ.get("EPUBVERI_BINARY") or plugin._binary_path()
    return path if os.path.isfile(path) else None


class BuildEpubTests(unittest.TestCase):
    def test_the_container_we_build_is_a_valid_ocf_zip(self):
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            epub, _workdir = plugin._build_epub(FakeBk(), tmp)
            with zipfile.ZipFile(epub) as zf:
                names = zf.namelist()
                first = zf.infolist()[0]
                # OCF: mimetype first, stored, exact bytes. epubveri checks all
                # three (PKG-006/PKG-007) and a deflated mimetype would make
                # every single run report a packaging error.
                self.assertEqual(first.filename, "mimetype")
                self.assertEqual(first.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(zf.read("mimetype"), b"application/epub+zip")
                self.assertIn("META-INF/container.xml", names)
                self.assertIn("OEBPS/Text/ch1.xhtml", names)
                self.assertEqual(len(names), len(FILES))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_line_and_column_map_to_a_character_offset(self):
        offsets = plugin._line_offsets("abc\ndefg\nhi")
        self.assertEqual(offsets[:4], [0, 4, 9, 11])


class PackageTests(unittest.TestCase):
    """The zip's *name* is part of Sigil's install contract, and getting it
    wrong is rejected outright with "Error: Plugin not a valid Sigil plugin"
    before a line of the plugin ever runs.

    `PluginDB::add_plugin` takes the zip's basename, truncates it at the
    **first** underscore, and requires every entry in the archive to sit under
    a folder of exactly that name, with `<name>/plugin.xml` among them. The
    first build named the archive `sigil_epubveri_v0.1.0.zip`, so Sigil looked
    for a folder called `sigil` and refused it. Nothing but installing it in
    Sigil could have caught that, which is why the rule is pinned here.
    """

    def test_the_archive_satisfies_sigils_install_contract(self):
        import zipfile as zf_mod
        sys.path.insert(0, PLUGIN_DIR)
        import build

        path = build.build()
        try:
            # Sigil's own derivation of the expected folder name.
            basename = os.path.splitext(os.path.basename(path))[0]
            expected = basename.split("_")[0]
            self.assertEqual(expected, build.FOLDER)

            with zf_mod.ZipFile(path) as zf:
                names = zf.namelist()
            self.assertTrue(names)
            for name in names:
                self.assertEqual(
                    name.split("/")[0], expected,
                    "%s is not under %s/, so verify_plugin_zip would reject "
                    "the archive" % (name, expected))
            self.assertIn("%s/plugin.xml" % expected, names)
            # And the things a user should get, but never the cached binary.
            self.assertIn("%s/README.md" % expected, names)
            self.assertIn("%s/LICENSE" % expected, names)
            self.assertFalse([n for n in names if n.endswith("/epubveri")])
            self.assertFalse([n for n in names if "/tests/" in n])
        finally:
            import shutil
            shutil.rmtree(os.path.dirname(path), ignore_errors=True)


class RunTests(unittest.TestCase):
    def setUp(self):
        if _binary() is None:
            self.skipTest("no epubveri binary; set EPUBVERI_BINARY")
        self._orig = plugin._binary_path
        plugin._binary_path = _binary

    def tearDown(self):
        plugin._binary_path = self._orig

    def test_findings_carry_a_full_bookpath_and_a_summary_is_added(self):
        bk = FakeBk()
        self.assertEqual(plugin.run(bk), 0)
        self.assertTrue(bk.results, "the run produced nothing")
        summary = bk.results[-1]
        self.assertEqual(summary[0], "info")
        self.assertIn("epubveri", summary[4])
        self.assertIn("NOT VALID", summary[4],
                      "the book has an empty dc:creator")
        # The empty dc:creator, reported against the package document by its
        # full path rather than "content.opf".
        creators = [r for r in bk.results if "dc:creator" in r[4]]
        self.assertEqual(len(creators), 1, bk.results)
        self.assertEqual(creators[0][1], "OEBPS/content.opf")
        self.assertEqual(creators[0][0], "error")

    def test_usage_is_hidden_by_default_and_shown_on_request(self):
        quiet = FakeBk()
        plugin.run(quiet)
        loud = FakeBk({"show_usage": True})
        plugin.run(loud)
        self.assertGreater(len(loud.results), len(quiet.results),
                           "-u should reveal the unused Misc/spare.xml note")
        self.assertTrue(any("OPF-097" in r[4] for r in loud.results),
                        [r[4] for r in loud.results])
        self.assertFalse(any("OPF-097" in r[4] for r in quiet.results))

    def test_advisory_is_off_by_default(self):
        off = FakeBk()
        plugin.run(off)
        self.assertFalse(any("[advisory:" in r[4] for r in off.results))


if __name__ == "__main__":
    unittest.main(verbosity=2)
