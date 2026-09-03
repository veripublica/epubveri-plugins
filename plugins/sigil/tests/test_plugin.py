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
import shutil
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: The repository root, where `icon.py` lives — one mark, both plugins.
ROOT = os.path.dirname(os.path.dirname(PLUGIN_DIR))
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


def _now():
    """Aware UTC, as the plugin writes it. `utcnow()` is deprecated in
    the Python Sigil bundles."""
    return datetime.now(timezone.utc)


class FakeBk(object):
    """The four container methods the plugin uses, and nothing else."""

    def __init__(self, prefs=None):
        # Seeded so the hourly update check is not due: these tests must not
        # touch the network, and a test that quietly does is a test that fails
        # on an aeroplane.
        self.prefs = {"last_update_check": _now().isoformat()}
        self.prefs.update(prefs or {})
        self.results = []
        self.get_opf_calls = 0

    def getPrefs(self):
        return self.prefs

    def savePrefs(self, prefs):
        self.prefs = prefs

    def get_opfbookpath(self):
        return "OEBPS/content.opf"

    def get_opf(self):
        """Sigil's re-serialisation, which is NOT what Code View shows.

        Deliberately different from the copied file — an extra line and the
        manifest rewritten — so that a plugin which goes back to substituting
        it fails on the position, not merely on the call count.
        """
        self.get_opf_calls += 1
        return OPF.replace("<manifest>", "<!-- rebuilt by Sigil -->\n  "
                                         "<manifest>")

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


def summary_of(texts, out):
    """The summary line, from wherever it went.

    It rides with the findings when there are any and is printed when there
    are none, so a test about what it *says* should not have to know which.
    The tests about where it *goes* are separate and explicit — that is the
    part that has been wrong three times.
    """
    rows = [t for t in texts if t.startswith("epubveri ")]
    return rows[-1] if rows else out


def run_capturing(bk):
    """`(result texts, stdout)`.

    The summary is printed rather than added, so every test that reads it has
    to read standard output. Sigil collects it the same way — `SavedStream`
    into the launcher's `<msg>`.
    """
    import contextlib
    import io as _io
    out = _io.StringIO()
    with contextlib.redirect_stdout(out):
        code = plugin.run(bk)
    return code, [r[4] for r in bk.results], out.getvalue()


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

    def test_the_opf_is_the_one_sigil_shows_not_a_rebuild(self):
        """Positions must land in the document Code View is displaying.

        The OPF is not a manifest item, so `copy_book_contents_to` fetches it
        through `Wrapper.readotherfile`, which returns `build_opf()` only when
        the book has unsaved OPF edits and the file from the ebook root
        otherwise. 0.1.0 overwrote it with `get_opf()` in every case, which
        replaced the text the user sees with a rebuild that sorts the manifest
        by id — so the panel's line number and the cursor referred to different
        documents. Reported as content.opf saying 95 and highlighting 96.
        """
        bk = FakeBk()
        tmpdir = tempfile.mkdtemp(prefix="epubveri-test-")
        try:
            _epub, workdir = plugin._build_epub(bk, tmpdir)
            with open(os.path.join(workdir, "OEBPS", "content.opf"),
                      encoding="utf-8") as handle:
                written = handle.read()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        self.assertEqual(written, OPF)
        self.assertEqual(bk.get_opf_calls, 0,
                         "the OPF Sigil displays was replaced by a rebuild")

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
            #
            # Three values, matching the real signature: the archive hash for
            # the next update check and the binary's own for the per-run
            # integrity check. Getting this wrong is how a tuple-unpacking bug
            # once looked exactly like "there was no update" - the broad
            # `except` around the check swallows our mistakes as readily as it
            # swallows a dead network.
            sha = expected if expected is not None else remote
            self.downloads.append(sha)
            path = plugin._binary_path()
            # In the first-install test the path does not exist yet, which is
            # the whole point of that case.
            binary_sha = (bin_mod.sha256_of(path) if os.path.isfile(path)
                          else "c" * 64)
            return path, sha, binary_sha

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

        old = _now() - timedelta(hours=2)
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

    def _allows(self, prefs):
        self._fake(remote=self.SHA_B)
        base = {"installed_sha256": self.SHA_A, "last_update_check": None}
        base.update(prefs)
        plugin._ensure_binary(FakeBk(base))
        return bool(self.downloads)

    def test_a_replaced_binary_is_not_run(self):
        """Verifying at download proves what arrived, not what runs.

        Between the two sits everything that can touch a file: a bad sync, a
        partial write, another program, or something worse. Hashing the 2.8 MB
        binary costs 1.8 ms — under one percent of a validation — so there is
        no reason to trust yesterday's answer.
        """
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp()
        fake_binary = os.path.join(tmp, "epubveri")
        try:
            with open(fake_binary, "wb") as handle:
                handle.write(b"the verified one")
            good = bin_mod.sha256_of(fake_binary)
            plugin._binary_path = lambda: fake_binary

            # Unchanged: nothing to say.
            self.assertIsNone(
                plugin._integrity_failure(fake_binary, {"binary_sha256": good}))

            # Replaced: named, and the caller must not run it.
            with open(fake_binary, "wb") as handle:
                handle.write(b"something else entirely")
            note = plugin._integrity_failure(fake_binary,
                                             {"binary_sha256": good})
            self.assertIsNotNone(note)
            self.assertIn("has changed since it was verified", note)
            self.assertIn("was not run", note)

            self._fake(remote=self.SHA_A)
            path, message = plugin._ensure_binary(FakeBk({
                "installed_sha256": self.SHA_A, "binary_sha256": good}))
            self.assertIsNone(path, "a changed binary must not be handed back")
            self.assertIn("has changed", message)

            # No stored hash means the plugin was upgraded from a version that
            # did not record one - trusted once and recorded, not refused.
            prefs = {}
            self.assertIsNone(plugin._integrity_failure(fake_binary, prefs))
            self.assertEqual(prefs["binary_sha256"],
                             bin_mod.sha256_of(fake_binary))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_key_is_written_into_the_file_with_its_default(self):
        """Sigil has no settings screen, so the JSON is the only place to
        change this — and a key that is merely *honoured* would be invisible
        there. Writing it on the first run makes the file document itself."""
        self._fake(remote=self.SHA_A)
        bk = FakeBk({"installed_sha256": self.SHA_A, "last_update_check": None})
        plugin._ensure_binary(bk)
        self.assertIs(bk.prefs[plugin._UPDATE_KEY], True)

    def test_anything_that_is_not_clearly_yes_stops_the_network(self):
        """The direction matters more than the list.

        This value is typed by hand, so it will not always be one of ours:
        `hayır`, `nein`, `off`, or a typo. Listing what counts as *off* would
        read every one of those as consent and keep using someone's connection
        against their wishes — the worst thing this switch can do. Listing what
        counts as *on* fails the other way, which is recoverable and shows up
        in the report after a month.
        """
        for value in ("yes", "YES", " yes ", "true", "on", "1", True):
            self.downloads = []
            self.assertTrue(self._allows({plugin._UPDATE_KEY: value}),
                            "%r should allow updates" % (value,))
        for value in ("no", "No", "hayır", "nein", "off", "0", False, "",
                      "yse", "maybe"):
            self.downloads = []
            self.assertFalse(self._allows({plugin._UPDATE_KEY: value}),
                             "%r must not reach the network" % (value,))

    def test_turning_it_off_is_not_commented_on(self):
        self._fake(remote=self.SHA_B)
        _p, note = plugin._ensure_binary(FakeBk({
            "installed_sha256": self.SHA_A, "last_update_check": None,
            plugin._UPDATE_KEY: "no"}))
        self.assertEqual(self.downloads, [])
        self.assertIsNone(note)

    def test_the_age_line_survives_turning_updates_off(self):
        """Because it is not about the network.

        "This copy is 300 days old" is the explanation for a finding that
        looks wrong. Hiding it from the person most likely to hit one — who
        deliberately froze their binary — would be the wrong kindness. The
        wording changes so it does not read as a failure.
        """
        old = (datetime.now(timezone.utc) - timedelta(days=300)).isoformat()
        self._fake(remote=self.SHA_A)
        _p, note = plugin._ensure_binary(FakeBk({
            "installed_sha256": self.SHA_A,
            plugin._UPDATE_KEY: "no",
            "last_update_success": old,
        }))
        self.assertIn("300 days old", note)
        self.assertIn("update checks are off", note)
        self.assertNotIn("could not", note)

    def test_a_long_stretch_offline_eventually_says_the_copy_is_old(self):
        """Silent for a fortnight, one quiet line after a month.

        A user offline for a weekend is not missing anything and must not be
        told about the network. But after a month the copy in use may report
        something that has since been fixed, and then "this is old" is the
        explanation for a finding that looks wrong. It is information, not a
        warning: no error, no verdict change, nothing to do until there is a
        connection.

        The distinction that makes it possible is `last_update_success`.
        `last_update_check` is stamped even when the check fails — on purpose,
        so an offline machine tries once an hour rather than once a book — so
        it can never tell how old the binary actually is.
        """
        now = datetime.now(timezone.utc)
        for days, expected in ((2, None), (29, None), (45, "45 days old")):
            prefs = {
                "installed_sha256": self.SHA_A,
                "last_update_check": (now - timedelta(days=1)).isoformat(),
                "last_update_success": (now - timedelta(days=days)).isoformat(),
            }
            self._fake(remote=self.SHA_A, check_raises=OSError("no network"))
            _path, note = plugin._ensure_binary(FakeBk(prefs))
            if expected is None:
                self.assertIsNone(note, "%d days should say nothing" % days)
            else:
                self.assertIn(expected, note)

    def test_a_stamp_written_before_timezones_is_still_readable(self):
        """Naive stamps predate the move off the deprecated `utcnow()`. Reading
        them as UTC rather than discarding them keeps an upgrade from forcing a
        check on every existing install."""
        naive = (datetime.now(timezone.utc)
                 .replace(tzinfo=None) - timedelta(minutes=5)).isoformat()
        age = plugin._since(naive)
        self.assertIsNotNone(age)
        self.assertLess(age, timedelta(hours=1))
        self.assertIsNone(plugin._since("not a date"))
        self.assertIsNone(plugin._since(None))

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
            # And the half of the name Sigil ignores has to say which editor
            # this is for. Both plugins shipped `epubveri_vX.Y.Z.zip` until
            # PeterT pointed out that a downloaded file said nothing about
            # which one it was (MobileRead 374286 #275). The two rules pull
            # against each other — the folder name is fixed, the rest is free
            # — so both are asserted or a rename satisfies one and breaks the
            # other silently.
            self.assertIn("sigil", basename[len(expected):],
                          "%s does not say which editor it is for" % basename)

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
            # The icon Sigil looks for. It is loaded from the plugin folder by
            # name (`PluginDB::load_plugin` prefers svg to png), so leaving it
            # out of the archive is the same as not having one.
            self.assertIn("%s/plugin.svg" % expected, names)
            self.assertIn("%s/plugin.png" % expected, names)
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

    def test_findings_carry_a_full_bookpath_and_a_summary(self):
        bk = FakeBk()
        code, texts, out = run_capturing(bk)
        self.assertEqual(code, 0)
        self.assertTrue(bk.results, "the run produced nothing")
        summary = summary_of(texts, out)
        self.assertIn("NOT VALID", summary,
                      "the book has an empty dc:creator")
        # The empty dc:creator, reported against the package document by its
        # full path rather than "content.opf".
        creators = [r for r in bk.results if "dc:creator" in r[4]]
        self.assertEqual(len(creators), 1, bk.results)
        self.assertEqual(creators[0][1], "OEBPS/content.opf")
        self.assertEqual(creators[0][0], "error")

    def test_every_finding_reaches_the_panel_and_is_labelled(self):
        """Nothing is hidden by default — and nothing is ambiguous.

        The switches added for MobileRead 374939 #21 are off-switches: a user
        who never opens the JSON sees what this test sees. Every line says
        what it is, and an advisory is labelled ADVISORY and carries the
        sentence that keeps it from reading as the two tools disagreeing.
        """
        bk = FakeBk()
        code, texts, _out = run_capturing(bk)
        self.assertEqual(code, 0)

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
        _code, texts, out = run_capturing(FakeBk())
        summary = summary_of(texts, out)
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
        _code, texts, out = run_capturing(bk)
        self.assertIn("NOT VALID", summary_of(texts, out))
        errors = [r for r in bk.results if r[0] == "error"]
        self.assertFalse([r for r in errors if "ADVISORY" in r[4]],
                         "an advisory was given Sigil's error type")

    def test_no_result_is_given_an_empty_bookpath(self):
        """Sigil prints "*** Invalid Book Path Provided ***" for one.

        A result about the book as a whole has no file, and the empty string
        is how the table is told to complain about it rather than how it is
        told there is none. Reported by DNSB on Windows for the summary line
        (MobileRead 374939 #16); the same empty string was in seven other
        places, so this asserts over every result the run produces.
        """
        bk = FakeBk()
        run_capturing(bk)
        self.assertTrue(bk.results)
        self.assertFalse([r for r in bk.results if r[1] == ""],
                         "an empty bookpath reaches Sigil's result table")

    def test_a_failure_before_the_book_is_read_also_names_no_file(self):
        """The error paths carry the same rule, and none of them has a file
        to name — the binary is missing, or was replaced, or would not run."""
        def explode(_bk):
            raise OSError("no network")
        orig = plugin._ensure_binary
        plugin._ensure_binary = explode
        try:
            bk = FakeBk()
            # The reason is printed as well as added, so that it survives
            # Sigil discarding the results on a non-zero return. Swallow it
            # here rather than letting every run of the suite carry it.
            import contextlib
            import io as _io
            with contextlib.redirect_stdout(_io.StringIO()):
                self.assertEqual(plugin.run(bk), -1)
        finally:
            plugin._ensure_binary = orig
        self.assertEqual(len(bk.results), 1)
        self.assertEqual(bk.results[0][0], "error")
        self.assertNotEqual(bk.results[0][1], "")


class CleanBk(FakeBk):
    """The same book with its two errors repaired.

    What is left is exactly one usage note and one advisory, so this is the
    fixture that can make the results panel empty: hide both categories and
    there is nothing to say. That is the only way to reach the branch where a
    suppressed summary speaks anyway, and it is a real run rather than a
    stubbed one.
    """

    def copy_book_contents_to(self, destdir):
        files = dict(FILES)
        files["OEBPS/content.opf"] = OPF.replace(
            "<dc:creator></dc:creator>", "<dc:creator>A</dc:creator>")
        files["OEBPS/Text/ch1.xhtml"] = CH1.replace(' fake="x"', "")
        for name, text in files.items():
            path = os.path.join(destdir, name.replace("/", os.sep))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)


@unittest.skipIf(_binary() is None, "set EPUBVERI_BINARY")
class DisplaySettingsTests(unittest.TestCase):
    """The three off-switches from Doitsu, MobileRead 374939 #21.

    Every one of these was checked by reverting the change and watching it
    fail, which is the only thing that makes a green suite evidence.
    """

    def _run(self, prefs=None, bk=None):
        bk = bk or FakeBk(prefs)
        code, texts, self.out = run_capturing(bk)
        self.assertEqual(code, 0)
        return bk, texts

    def test_the_switches_are_written_into_the_file_on_first_run(self):
        """The JSON is the only place they can be changed, so it has to be the
        place they can be found. A key that were merely honoured would leave
        someone reading the file with no sign the choice exists."""
        bk, _ = self._run()
        for key in ("show_usage", "show_advisory", "show_summary"):
            self.assertIs(bk.prefs.get(key), True, bk.prefs)

    def test_show_usage_false_hides_usage_and_leaves_advisories(self):
        _bk, texts = self._run({"show_usage": False})
        self.assertFalse([t for t in texts if t.startswith("USAGE ")], texts)
        self.assertTrue([t for t in texts if t.startswith("ADVISORY ")], texts)
        # And the errors, which no switch touches.
        self.assertTrue([t for t in texts if t.startswith("ERROR ")], texts)

    def test_show_advisory_false_hides_advisories_and_leaves_usage(self):
        """The two switches must not do each other's job. `ADV-*` is emitted
        AT usage severity, so a filter written on severity alone would take
        the advisories out with `show_usage` and leave `show_advisory` with
        nothing to do."""
        _bk, texts = self._run({"show_advisory": False})
        self.assertFalse([t for t in texts if t.startswith("ADVISORY ")], texts)
        self.assertTrue([t for t in texts if t.startswith("USAGE ")], texts)

    def test_a_hidden_category_says_so_and_keeps_its_count(self):
        """The whole point. A panel with no usage notes must not read the same
        as a panel whose usage notes were filtered — this project has three
        defects on record whose only symptom was silence, and a settings-driven
        silence is the same shape. It is also the only way a Sigil user can
        discover that a switch exists at all."""
        _bk, texts = self._run({"show_usage": False, "show_advisory": False})
        summary = summary_of(texts, self.out)
        self.assertIn("1 usage note(s)", summary)
        self.assertIn("1 advisory finding(s) epubcheck does not make", summary)
        self.assertIn("hidden by your settings", summary)
        self.assertNotIn("also listed", summary)

    def test_hiding_does_not_change_what_the_validator_was_asked(self):
        """`-u --advisory` go on every run whatever the settings say, so the
        numbers describe the book and not the preferences. Compare the two
        summaries: the same counts, differently placed."""
        _bk, texts = self._run()
        shown = summary_of(texts, self.out)
        _bk, texts = self._run({"show_usage": False, "show_advisory": False})
        hidden = summary_of(texts, self.out)
        for fragment in ("2 error(s)", "1 usage note(s)",
                         "1 advisory finding(s)"):
            self.assertIn(fragment, shown)
            self.assertIn(fragment, hidden)

    def test_an_unrecognised_value_shows_rather_than_hides(self):
        """The direction, and it is the opposite of `autoupdate`'s.

        There an unrecognised value must mean *off*, because the switch spends
        someone's connection. Here the harmful direction is hiding a finding:
        a reader who types `flase` and is silently shown less than the
        validator found has no way to notice.
        """
        for typo in ("flase", "hayır", "", "maybe"):
            _bk, texts = self._run({"show_usage": typo})
            self.assertTrue([t for t in texts if t.startswith("USAGE ")],
                            "%r hid a finding" % typo)

    def test_the_off_spellings_a_hand_edited_file_will_contain(self):
        """A JSON boolean is what the file is written with, but what comes
        back is whatever was typed over it."""
        for off in (False, "false", "False", "no", "off", "0", "N", " no "):
            _bk, texts = self._run({"show_usage": off})
            self.assertFalse([t for t in texts if t.startswith("USAGE ")],
                             "%r did not hide" % (off,))

    def test_show_summary_false_says_nothing_anywhere(self):
        """The only switch that removes something outright. It can, because
        the line was never load-bearing: Sigil writes "Validation Tool
        Reported No Problems Found" into an empty panel by itself."""
        _bk, texts = self._run({"show_summary": False})
        self.assertTrue(texts, "the findings went with the summary")
        self.assertNotIn("epubveri ", self.out)

    def test_a_clean_book_leaves_the_results_table_empty(self):
        """The one that matters to an automation list, and the regression
        this whole shape exists to prevent.

        Sigil's Automation has three outcomes for a validation plugin, named
        in its own binary: "Validation Tool Reported No Problems Found",
        "Aborted due to Validation Errors", "Ignored Validation Errors". Zero
        results is the first and **one result of any severity is the second**,
        `info` included. A summary row therefore stopped every automation list
        containing this plugin, on every book, clean ones included — DNSB,
        MobileRead 374939 #23 and #29, confirmed by BeckyEbook in #28 by
        removing the line.
        """
        _bk, texts = self._run(bk=CleanBk({"show_usage": False,
                                           "show_advisory": False}))
        self.assertEqual(texts, [], "an automation list would abort on these")
        # With nothing to sit beside it goes to the one channel left.
        self.assertIn("VALID", self.out)
        self.assertIn("hidden by your settings", self.out)

    def test_the_summary_rides_with_the_findings_when_there_are_any(self):
        """Where a reader is actually looking.

        Adding it beside real findings costs an automation list nothing: the
        list was going to abort on those findings anyway. And the Plugin
        Runner window, which is where a printed line goes, is not shown at all
        for a run that succeeds — `<autostart>true</autostart>` sends Sigil
        straight to the results.
        """
        for prefs in ({}, {"show_summary": True}, {"show_usage": False},
                      {"show_advisory": False}):
            _bk, texts = self._run(dict(prefs))
            rows = [t for t in texts if t.startswith("epubveri ")]
            self.assertEqual(len(rows), 1,
                             "%r did not put the summary in the table"
                             % (prefs,))
            self.assertNotIn("epubveri ", self.out,
                             "%r also printed it" % (prefs,))


@unittest.skipIf(_binary() is None, "set EPUBVERI_BINARY")
class PluginVersionTests(unittest.TestCase):
    """Doitsu, MobileRead 374939 #21: "add the plugin version number for
    debugging purposes"."""

    def test_the_version_is_read_from_plugin_xml_and_not_duplicated(self):
        with open(os.path.join(plugin._plugin_dir(), "plugin.xml"),
                  encoding="utf-8") as handle:
            declared = handle.read()
        version = plugin._plugin_version()
        self.assertTrue(version, "no version found in plugin.xml")
        self.assertIn("<version>%s</version>" % version, declared)

    def test_the_summary_names_both_versions(self):
        """epubveri's says which validator produced the findings; the
        plugin's says which code turned them into rows, and most of the
        defects found so far were on this side of that line."""
        _code, texts, out = run_capturing(FakeBk())
        self.assertIn("(plugin %s)" % plugin._plugin_version(),
                      summary_of(texts, out))

    def test_an_unreadable_plugin_xml_gives_no_version_rather_than_a_wrong_one(self):
        """The line exists to be pasted into a bug report, so a guess is worse
        than an absence."""
        real = plugin._plugin_dir
        plugin._plugin_dir = lambda: os.path.join(os.path.dirname(__file__),
                                                  "no-such-dir")
        try:
            self.assertIsNone(plugin._plugin_version())
        finally:
            plugin._plugin_dir = real


class IconTests(unittest.TestCase):
    """Sigil looks for `plugin.svg` and falls back to `plugin.png`, so the two
    have to agree — and nothing but this notices when they stop. A mark edited
    in one and not the other is a difference only somebody running the other
    platform would ever see.

    Needs no epubveri binary: it is about the shipped files, not a validation.
    """

    def _icon(self):
        import importlib.util
        path = os.path.join(ROOT, "icon.py")
        # By path, and under a name of its own: `import icon` inside Sigil or
        # calibre finds whatever else is called that.
        spec = importlib.util.spec_from_file_location("epubveri_sigil_icon",
                                                      path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_shipped_svg_is_the_one_icon_py_writes(self):
        icon = self._icon()
        with open(os.path.join(plugin._plugin_dir(), "plugin.svg"),
                  encoding="utf-8") as handle:
            self.assertEqual(handle.read(), icon.SVG,
                             "plugin.svg was hand-edited; run icon.py")

    def test_the_shipped_png_is_the_one_icon_py_draws(self):
        import tempfile
        icon = self._icon()
        with open(os.path.join(plugin._plugin_dir(), "plugin.png"), "rb") as h:
            shipped = h.read()
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            icon.write_png(path, 128)
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), shipped,
                                 "plugin.png does not match the geometry; "
                                 "run icon.py")
        finally:
            os.unlink(path)

    def test_both_plugins_ship_the_same_drawing(self):
        """One mark, three files, two editors. Nothing but this notices when
        they stop agreeing, and a divergence is visible only to somebody
        running the editor whose copy went stale."""
        sigil = os.path.join(plugin._plugin_dir(), "plugin.png")
        calibre = os.path.join(ROOT, "plugins", "calibre", "plugin.png")
        with open(sigil, "rb") as a, open(calibre, "rb") as b:
            self.assertEqual(a.read(), b.read(),
                             "the two plugins' icons have diverged; "
                             "run icon.py")

    def test_the_mark_fills_the_grid_it_shares_with_its_alternatives(self):
        """The first draft of this mark stood 35x52 against a 60x60 tile and
        read small for a real reason rather than an optical one. Height is the
        dimension that has to match; a page is narrower than a tile by
        definition."""
        icon = self._icon()
        x0, y0, x1, y1 = icon.RECT
        self.assertEqual((x1 - x0, y1 - y0), (44.0, 60.0))
        self.assertEqual(y1 - y0, icon.GRID - 2 * y0)

    def test_nothing_in_the_mark_vanishes_at_16px(self):
        """The thinnest thing on screen is the tick. At 16 px one grid unit is
        a quarter of a pixel, so a stroke under about 4 units is a mark you
        cannot see on the platform this was raised about."""
        icon = self._icon()
        self.assertGreaterEqual(icon.TICK_WIDTH * 16 / icon.GRID, 1.5)


@unittest.skipIf(_binary() is None, "set EPUBVERI_BINARY")
class ExitCodeTests(unittest.TestCase):
    """What Sigil is told, as opposed to what the panel shows.

    `PluginRunner::launch` checks the return value before it copies the
    plugin's results into the wrapper XML: on anything non-zero it writes
    `<result>failed</result>` and returns early, so every `add_result` is
    discarded. Standard output survives on both paths. Read off Sigil's own
    `plugin_launchers/python/launcher.py`.

    DNSB reported an automation erroring on every run after swapping epubcheck
    for this plugin (MobileRead 374939 #23), and DiapDealer answered that any
    non-zero return is an error to Sigil (#24). These pin our side of that.
    """

    def test_a_completed_validation_returns_zero_however_the_book_is(self):
        """Valid or not, the plugin did its job. The verdict belongs in the
        panel; the return value says whether epubveri ran."""
        self.assertEqual(run_capturing(FakeBk())[0], 0, "an invalid book")
        self.assertEqual(run_capturing(CleanBk())[0], 0, "a clean book")

    def test_a_failure_says_why_on_stdout_where_it_survives(self):
        """The reason must not be an add_result and nothing else: on a
        non-zero return Sigil throws the results away and the user is told the
        plugin failed with no word about why."""
        import contextlib
        import io as _io

        real = plugin._ensure_binary
        plugin._ensure_binary = lambda bk: (_ for _ in ()).throw(
            RuntimeError("no build for sparc"))
        try:
            bk = FakeBk()
            out = _io.StringIO()
            with contextlib.redirect_stdout(out):
                code = plugin.run(bk)
        finally:
            plugin._ensure_binary = real

        self.assertEqual(code, -1)
        self.assertIn("sparc", out.getvalue(),
                      "the reason never left the results table")
        self.assertTrue(out.getvalue().startswith("epubveri"),
                        out.getvalue())


@unittest.skipIf(_binary() is None, "set EPUBVERI_BINARY")
class SuiteHygieneTests(unittest.TestCase):
    def test_no_test_lets_the_plugins_output_escape(self):
        """The summary and every failure reason are printed now, so a test
        that calls `run` without capturing writes into the suite's own output.
        Three did, and the noise is indistinguishable from a real message —
        which is the whole reason those lines are printed in the first place.
        """
        import contextlib
        import io as _io
        import unittest as _ut

        loader = _ut.TestLoader()
        suite = _ut.TestSuite()
        for group in loader.loadTestsFromModule(sys.modules[__name__]):
            for case in group:
                # Itself excluded by identity, not by name: a filter that
                # matches on a string is one rename away from recursing.
                if type(case) is not SuiteHygieneTests:
                    suite.addTest(case)
        out, err = _io.StringIO(), _io.StringIO()
        with contextlib.redirect_stdout(out):
            _ut.TextTestRunner(stream=err, verbosity=0).run(suite)
        self.assertEqual(out.getvalue(), "",
                         "a test printed instead of capturing:\n"
                         + out.getvalue()[:400])


if __name__ == "__main__":
    unittest.main(verbosity=2)
