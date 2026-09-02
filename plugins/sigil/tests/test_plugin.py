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
from datetime import datetime, timedelta

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)

import plugin  # noqa: E402
from client import binary as bin_mod  # noqa: E402
from client import runner  # noqa: E402


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
# `fake` draws a message that QUOTES the attribute name (the shape that broke
# Sigil's result XML), and `colour` draws an ADV-001 advisory - the two things
# the display layer has to get right.
CH1 = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">'
       '<head><title>t</title>'
       '<style type="text/css">p { colour: red }</style></head>'
       '<body><p fake="x">x</p></body></html>')
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
        # Seeded so the daily update check is not due: these tests must not
        # touch the network, and a test that quietly does is a test that fails
        # on an aeroplane.
        self.prefs = {"last_update_check": datetime.utcnow().isoformat()}
        self.prefs.update(prefs or {})
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
        """The offset must land on the character epubveri named.

        The version of this test that only checked `_line_offsets` passed
        while every finding pointed one line late — Sigil reported line 283
        and highlighted 284 — because the bug was in the *use* of that list,
        not in the list. So this asserts the character at the offset, which is
        the only thing that can be wrong in a way a user sees.
        """
        offsets = plugin._line_offsets("abc\ndefg\nhi")
        self.assertEqual(offsets[:4], [0, 4, 9, 11])

        import shutil
        import tempfile
        text = "<html>\n  <body>\n    <p bad=\"x\">hello</p>\n  </body>\n</html>\n"
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, "f.xhtml"), "w", encoding="utf-8") as h:
                h.write(text)
            cases = [
                (1, 1, "<html>"),      # the very first character
                (2, 3, "<body>"),      # a column inside an indented line
                (3, 5, "<p bad="),     # the shape a real finding points at
                (5, 1, "</html>"),     # the last line
            ]
            for line, column, expected in cases:
                offset = plugin._char_offset(tmp, "f.xhtml", line, column)
                self.assertIsNotNone(offset, (line, column))
                self.assertTrue(
                    text[offset:].startswith(expected),
                    "line %d column %d gave offset %d, which is %r, not %r"
                    % (line, column, offset, text[offset:offset + 8], expected))
            # Out of range asks Sigil to fall back to the line number rather
            # than pointing somewhere arbitrary.
            self.assertIsNone(plugin._char_offset(tmp, "f.xhtml", 99, 1))
            self.assertIsNone(plugin._char_offset(tmp, "f.xhtml", 0, 1))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ResultXmlTests(unittest.TestCase):
    """Everything we hand Sigil ends up inside a double-quoted XML attribute,
    built by raw interpolation in its launcher with no escaping:

        '<validationresult type="%s" bookpath="%s" linenumber="%s"
          charoffset="%s" message="%s" />'

    So one unescaped `"` in a message ends the attribute and Sigil answers
    "Error Parsing Result XML" — with **no findings shown at all**, which is
    how this was found: a book with 257 findings displayed none of them.

    These tests rebuild that exact line and parse it, so they fail the way
    Sigil failed rather than on a rule of our own invention.
    """

    LINE = ('<validationresult type="%s" bookpath="%s" linenumber="%s" '
            'charoffset="%s" message="%s" />')

    def _roundtrip(self, message, bookpath="OEBPS/x.xhtml"):
        from xml.etree import ElementTree as ET
        doc = self.LINE % ("error", plugin._xml_attr(bookpath), "1", "0",
                           plugin._xml_attr(message))
        node = ET.fromstring(doc)          # raises if we broke the document
        return node.get("message"), node.get("bookpath")

    def test_a_quoted_element_name_survives(self):
        # The commonest shape epubveri produces, and the one that broke it.
        message = 'attribute "name" not allowed here'
        got, _ = self._roundtrip(message)
        self.assertEqual(got, message)

    def test_ampersands_and_angle_brackets_survive(self):
        for message in ('a bare & is not a character reference',
                        'element <p> is not allowed here',
                        'value "a<b&c>d" is invalid',
                        "file name 'x' contains a space"):
            got, _ = self._roundtrip(message)
            self.assertEqual(got, message, message)

    def test_a_path_with_an_ampersand_survives(self):
        _, path = self._roundtrip("x", bookpath="OEBPS/Text/a&b.xhtml")
        self.assertEqual(path, "OEBPS/Text/a&b.xhtml")

    def test_single_quotes_are_left_alone(self):
        # Legal inside a double-quoted attribute, and epubveri uses them far
        # more often than double quotes — escaping them would be noise.
        self.assertEqual(plugin._xml_attr("file 'x' is odd"),
                         "file 'x' is odd")


class UpdateTests(unittest.TestCase):
    """The plugin keeps epubveri current on its own.

    Without it a user is pinned to whatever shipped the day they installed —
    and almost every recent epubveri release fixed a *wrong error on a valid
    book*, so a stale binary keeps telling its owner something we already know
    is untrue.

    The check is a **checksum** comparison, not a version comparison: 842 bytes
    of `SHA256SUMS.txt` against one stored string, with no GitHub API and no
    `epubveri -V`. It is also stricter — it notices an archive re-uploaded
    under the same tag and a local copy that has been replaced. Nothing here
    may stop a validation, so every failure path is checked too.
    """

    SHA_A = "a" * 64
    SHA_B = "b" * 64

    def setUp(self):
        self.downloads = []
        self._orig = (bin_mod.latest_checksums, bin_mod.download_binary,
                      runner.binary_version, plugin._binary_path)
        plugin._binary_path = lambda: __file__      # any existing file

    def tearDown(self):
        (bin_mod.latest_checksums, bin_mod.download_binary,
         runner.binary_version, plugin._binary_path) = self._orig

    def _fake(self, remote=SHA_A, check_raises=None, download_raises=None,
              versions=("epubveri 0.13.3", "epubveri 0.14.0")):
        def latest_checksums(timeout=None):
            if check_raises:
                raise check_raises
            return {bin_mod.asset_name(): remote}

        def download_binary(destdir, expected=None, timeout=None):
            if download_raises:
                raise download_raises
            # The real one fetches SHA256SUMS.txt itself when the caller has
            # no expectation - the first install - and returns the hash it
            # verified against either way. A fake that echoed `expected` would
            # model that wrong and let a first-install bug through.
            sha = expected if expected is not None else remote
            self.downloads.append(sha)
            return plugin._binary_path(), sha

        seen = iter(versions)
        bin_mod.latest_checksums = latest_checksums
        bin_mod.download_binary = download_binary
        runner.binary_version = lambda b, timeout=15: next(seen, versions[-1])

    def test_a_changed_checksum_is_fetched_and_announced(self):
        self._fake(remote=self.SHA_B)
        bk = FakeBk({"last_update_check": None, "installed_sha256": self.SHA_A})
        _path, note = plugin._ensure_binary(bk)
        self.assertEqual(self.downloads, [self.SHA_B])
        self.assertEqual(note, "updated epubveri 0.13.3 to 0.14.0")
        # The new hash is stored, or the next check downloads it again.
        self.assertEqual(bk.prefs["installed_sha256"], self.SHA_B)

    def test_an_unchanged_checksum_downloads_nothing(self):
        self._fake(remote=self.SHA_A)
        _path, note = plugin._ensure_binary(
            FakeBk({"last_update_check": None, "installed_sha256": self.SHA_A}))
        self.assertEqual(self.downloads, [], "1.1 MB fetched for nothing")
        self.assertIsNone(note)

    def test_it_checks_once_an_hour_and_not_once_a_run(self):
        self._fake(remote=self.SHA_B)
        recent = FakeBk({"installed_sha256": self.SHA_A})   # checked just now
        plugin._ensure_binary(recent)
        self.assertEqual(self.downloads, [], "checked again within the hour")

        old = datetime.utcnow() - timedelta(hours=2)
        stale = FakeBk({"last_update_check": old.isoformat(),
                        "installed_sha256": self.SHA_A})
        plugin._ensure_binary(stale)
        self.assertEqual(len(self.downloads), 1)

    def test_a_failure_neither_raises_nor_retries_every_run(self):
        for raiser in ({"check_raises": OSError("no network")},
                       {"download_raises": OSError("disk full")}):
            self.downloads = []
            self._fake(remote=self.SHA_B, **raiser)
            bk = FakeBk({"last_update_check": None,
                         "installed_sha256": self.SHA_A})
            path, note = plugin._ensure_binary(bk)   # must not raise
            self.assertIsNotNone(path, "validation must continue")
            self.assertIsNone(note)
            # The attempt is recorded, so an offline machine makes one failed
            # request an hour rather than one per book.
            self.assertTrue(bk.prefs.get("last_update_check"))
            # ...and a failed download must not claim the new hash is installed.
            self.assertEqual(bk.prefs["installed_sha256"], self.SHA_A)

    def test_an_offline_user_with_a_binary_sees_no_network_error(self):
        """The common case, and it must be invisible.

        Someone who installed the plugin once and then works on a train still
        has a working validator. The hourly check fails, is recorded, and says
        nothing — a validator that complains about the network while happily
        validating would be reporting its own plumbing.
        """
        self._fake(remote=self.SHA_B, check_raises=OSError("no network"))
        bk = FakeBk({"last_update_check": None, "installed_sha256": self.SHA_A})
        path, note = plugin._ensure_binary(bk)
        self.assertIsNotNone(path)
        self.assertIsNone(note)

    def test_a_first_install_without_a_network_says_something_usable(self):
        """The uncommon case, where an error IS right: with no binary there is
        nothing to validate with. But the raw exception is developer text."""
        message = plugin._install_failure(
            OSError("<urlopen error [Errno 8] nodename nor servname provided>"))
        self.assertIn("needs an internet connection", message)
        self.assertIn("works offline", message)
        self.assertNotIn("Errno 8", message.split("(")[0])   # detail, not lede

        # Our own DownloadError messages are already written for a reader and
        # must pass through rather than be relabelled as a network problem.
        own = bin_mod.DownloadError("no epubveri build for this platform")
        self.assertEqual(plugin._install_failure(own),
                         "epubveri could not be installed: "
                         "no epubveri build for this platform")

    def test_an_unreadable_timestamp_is_treated_as_never_checked(self):
        self._fake(remote=self.SHA_B)
        plugin._ensure_binary(FakeBk({"last_update_check": "not a date",
                                      "installed_sha256": self.SHA_A}))
        self.assertEqual(len(self.downloads), 1)

    def test_the_first_install_stores_its_checksum(self):
        self._fake(remote=self.SHA_B)
        missing = os.path.join(os.path.dirname(__file__), "no-such-binary")
        plugin._binary_path = lambda: missing
        bk = FakeBk()
        _path, note = plugin._ensure_binary(bk)
        self.assertEqual(note, "installed epubveri")
        self.assertEqual(bk.prefs["installed_sha256"], self.SHA_B)


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

    def test_every_finding_reaches_the_panel_and_is_labelled(self):
        """No settings, so nothing is hidden — and nothing is ambiguous.

        Sigil gives a plugin no configuration screen, so a preference would be
        a switch the user cannot reach. Everything is shown instead, and every
        line says what it is: an advisory is labelled ADVISORY and carries the
        sentence that keeps it from reading as the two tools disagreeing.
        """
        bk = FakeBk()
        self.assertEqual(plugin.run(bk), 0)
        texts = [r[4] for r in bk.results]

        # The unreferenced Misc/spare.xml: a usage note, previously hidden.
        self.assertTrue(any("USAGE OPF-097" in t for t in texts), texts)
        # The CSS typo: an advisory, previously hidden.
        advisories = [t for t in texts if "ADVISORY ADV-001" in t]
        self.assertEqual(len(advisories), 1, texts)
        self.assertIn("epubcheck does not report this", advisories[0])
        self.assertIn("the verdict is unaffected", advisories[0])
        # An ordinary error keeps epubveri's own severity word.
        self.assertTrue(any(t.startswith("ERROR RSC-005") for t in texts), texts)

    def test_the_summary_separates_what_decides_the_verdict(self):
        bk = FakeBk()
        plugin.run(bk)
        summary = bk.results[-1][4]
        # Errors and warnings decide it; the rest is listed as not deciding it.
        self.assertIn("2 error(s)", summary)
        self.assertIn("1 usage note(s)", summary)
        self.assertIn("1 advisory finding(s) epubcheck does not make", summary)
        self.assertIn("neither affects the verdict", summary)
        # Advisories are emitted at usage severity, so a naive count would
        # report them twice.
        self.assertNotIn("2 usage note(s)", summary)

    def test_advisory_findings_never_move_the_verdict(self):
        """The promise the family rests on, checked at the plugin's own
        boundary rather than trusted from the library. The fixture is NOT
        VALID for reasons that have nothing to do with the advisory, and the
        advisory must not be among the counted errors."""
        bk = FakeBk()
        plugin.run(bk)
        summary = bk.results[-1][4]
        self.assertIn("NOT VALID", summary)
        errors = [r for r in bk.results if r[0] == "error"]
        self.assertFalse([r for r in errors if "ADVISORY" in r[4]],
                         "an advisory was given Sigil's error type")


if __name__ == "__main__":
    unittest.main(verbosity=2)
