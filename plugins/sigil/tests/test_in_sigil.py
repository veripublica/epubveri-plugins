# epubveri for Sigil — run the plugin inside Sigil's own launcher
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the GNU
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See the LICENSE file at the root of this
# repository.
"""Drive the plugin through **Sigil's own `launcher.py`**, with no GUI.

`test_plugin.py` calls `plugin.run(bk)` against a container of its own making,
which is the right shape for most of what can break — but it is our idea of
what Sigil does. This file is Sigil's: the installed `launcher.py`, its
`Wrapper`, its `ValidationContainer`, its result XML, and its bundled Python.
The only thing missing is the window.

**Its own docstring used to say "Sigil cannot be scripted".** That was true of
the GUI and false of the launcher, and believing it is what kept every Sigil
contract in this plugin a thing learned by installing a zip and clicking. Five
of them were learned that way; each cost a release. What is pinned here is the
handful that only a real launcher run can show:

* the result XML **parses** — Sigil writes our `message` into an attribute
  without escaping it, so an unescaped `"` or `&` from a finding produces
  malformed XML and Sigil shows nothing at all;
* a finding's `bookpath` is container-relative, not a basename;
* `charoffset` is absolute, and Sigil prefers it to the line number;
* the summary row carries a **space** as its bookpath — an empty one is read
  as a complaint about the plugin;
* the display settings are written on first run, and the three sort orders
  come out in three different orders.

Skipped, not failed, when Sigil is not installed: it is a macOS/Linux desktop
application and this suite has to stay runnable without it.

**The name has to start with `test`** — the documented way to run this suite
is `python3 -m unittest discover -s plugins/sigil/tests`, whose default
pattern is `test*.py`. Called anything else this file is in the repository and
run by nobody, which is the fate of the scratchpad it came from and the same
shape as the shelf scan that reported "no findings" for a week because its
binary had moved.

    python3 plugins/sigil/tests/test_in_sigil.py
    SIGIL_APP=/path/to/Sigil.app/Contents python3 …/test_in_sigil.py
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TESTS_DIR)
ROOT = os.path.dirname(os.path.dirname(PLUGIN_DIR))

#: The installed Sigil. `Contents` is the macOS shape; a Linux build lays the
#: same two paths out under its own prefix, which is why the override exists
#: rather than a second hard-coded guess.
SIGIL = os.environ.get("SIGIL_APP", "/Applications/Sigil.app/Contents")
LAUNCHER = os.path.join(SIGIL, "plugin_launchers", "python", "launcher.py")


def _sigil_python():
    """Sigil's bundled interpreter, whatever version it currently ships.

    Pinned to 3.14 while this lived in a scratchpad, which would have broken
    on the next Sigil release with a message about a missing file rather than
    about a moved one.
    """
    versions = os.path.join(SIGIL, "Frameworks", "Python.framework", "Versions")
    if os.path.isdir(versions):
        for name in sorted(os.listdir(versions), reverse=True):
            if name == "Current":
                continue
            candidate = os.path.join(versions, name, "bin", "python3")
            if os.path.isfile(candidate):
                return candidate
    # A Linux build runs plugins with the system interpreter.
    return sys.executable


def _binary():
    """The epubveri the plugin should run, without going near the network."""
    explicit = os.environ.get("EPUBVERI_BINARY")
    if explicit and os.path.isfile(explicit):
        return explicit
    for candidate in (
        os.path.join(PLUGIN_DIR, "epubveri"),
        os.path.expanduser(
            "~/Library/Preferences/calibre/plugins/epubveri-data/epubveri"),
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


def _why_skip():
    if not os.path.isfile(LAUNCHER):
        return "Sigil is not installed (no launcher.py at %s)" % LAUNCHER
    if _binary() is None:
        return ("no epubveri binary — put one at plugins/sigil/epubveri "
                "or set EPUBVERI_BINARY")
    return None


SKIP = _why_skip()


def _fixture():
    """`test_plugin.py`'s book, so the two suites describe one book.

    Loaded by path rather than imported: this file may be run directly, and
    the sibling's name is not on `sys.path` then. Module level only — its
    tests are behind a `__main__` guard.
    """
    spec = importlib.util.spec_from_file_location(
        "sigil_fixture", os.path.join(TESTS_DIR, "test_plugin.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Run(object):
    """One launcher run, and everything it left behind."""

    def __init__(self, returncode, stdout, stderr, prefs):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.prefs = prefs
        # The launcher prints the XML and Sigil's own parser warnings; only
        # the wrapper element is ours.
        start = stdout.find("<wrapper")
        end = stdout.find("</wrapper>")
        self.xml = stdout[start:end + len("</wrapper>")] if start >= 0 else ""

    @property
    def results(self):
        """`<validationresult>` elements, in the order Sigil received them."""
        return list(ET.fromstring(self.xml).iter("validationresult"))


def run_in_sigil(sort=None, show=None):
    """Stage a plugin directory and a book, and run Sigil's launcher over it.

    Nothing here is left in the repository: the plugin is *copied* into a
    temporary directory, exactly as installing the zip would, so a run cannot
    pick up a stray file next to the source.
    """
    fixture = _fixture()
    tmp = tempfile.mkdtemp(prefix="sigil-launch-")
    try:
        root = os.path.join(tmp, "root")
        out = os.path.join(tmp, "out")
        target = os.path.join(tmp, "plugins", "epubveri")
        usrsup = os.path.join(tmp, "usrsup")
        for path in (root, out, target, usrsup):
            os.makedirs(path)

        for name, text in fixture.FILES.items():
            path = os.path.join(root, *name.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)

        for name in ("plugin.py", "plugin.xml"):
            shutil.copy2(os.path.join(PLUGIN_DIR, name), target)
        shutil.copytree(os.path.join(PLUGIN_DIR, "client"),
                        os.path.join(target, "client"))
        binary = os.path.join(target, "epubveri")
        shutil.copy2(_binary(), binary)
        os.chmod(binary, 0o755)

        prefs_dir = os.path.join(tmp, "plugins_prefs", "epubveri")
        os.makedirs(prefs_dir)
        prefs_path = os.path.join(prefs_dir, "epubveri.json")
        # **`autoupdate` off is not a detail.** Left on, a test run asks
        # GitHub for the newest release and may download a binary — a suite
        # that reaches the network is a suite that fails on a train.
        seed = {"autoupdate": False}
        if sort is not None:
            seed["sort"] = sort
        if show is not None:
            seed.update(show)
        with open(prefs_path, "w", encoding="utf-8") as handle:
            json.dump(seed, handle)

        # Sigil hands the launcher its settings as a bare list of lines. The
        # order is `launcher.py`'s and nothing names the fields, so this is a
        # transcription of what Sigil writes, not a structure of ours.
        with open(os.path.join(out, "sigil.cfg"), "w",
                  encoding="utf-8") as handle:
            handle.write("\n".join([
                "OEBPS/content.opf", os.path.join(SIGIL, "MacOS"), usrsup,
                "en", "en_US", "False", os.path.join(tmp, "book.epub"),
                "light", "", "detect", "", "NotInAutomate", "", "", ""]))

        proc = subprocess.run(
            [_sigil_python(), LAUNCHER, root, out, "validation",
             os.path.join(target, "plugin.py")],
            capture_output=True, text=True, timeout=180)
        with open(prefs_path, encoding="utf-8") as handle:
            prefs = json.load(handle)
        return Run(proc.returncode, proc.stdout, proc.stderr, prefs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _codes(run):
    """`("ERROR RSC-005", "USAGE OPF-097", …)` for the non-summary rows."""
    out = []
    for element in run.results:
        if element.get("linenumber") == "-1":
            continue
        # `ERROR RSC-005: text…` — the id keeps the colon that joins it
        # to the message, so it comes off here rather than in every
        # expectation below.
        out.append(" ".join(element.get("message", "").split()[:2]).rstrip(":"))
    return out


@unittest.skipIf(SKIP, SKIP or "")
class LauncherTests(unittest.TestCase):
    """One run for everything that does not need its own settings."""

    @classmethod
    def setUpClass(cls):
        # Not `cls.run`: that is `TestCase.run`, and shadowing it makes
        # unittest call this object instead of the test.
        cls.once = run_in_sigil()

    def test_the_launcher_completes_and_calls_the_run_a_success(self):
        self.assertEqual(self.once.returncode, 0, self.once.stderr[:2000])
        self.assertEqual(
            ET.fromstring(self.once.xml).findtext("result"), "success")

    def test_the_result_xml_parses_because_we_escape_what_sigil_will_not(self):
        """Sigil interpolates our message into an XML attribute as it stands.

        A finding quoting an attribute name — `attribute "fake" is not allowed
        here` — therefore reaches the document with real quotes in it unless
        the plugin escapes them first, and Sigil then shows nothing at all
        rather than a broken row. The fixture book carries exactly that
        finding, which is why this assertion is worth its runtime: parsing is
        the only check that fails when the escaping goes.
        """
        self.assertIn("&quot;", self.once.xml)
        messages = [e.get("message") for e in self.once.results]
        self.assertTrue(
            any('attribute "fake"' in m for m in messages),
            "the fixture's quoted-attribute finding is gone; this test is "
            "then asserting nothing — restore it or repoint the test")

    def test_a_finding_is_located_by_its_container_relative_path(self):
        paths = {e.get("bookpath") for e in self.once.results
                 if e.get("linenumber") != "-1"}
        self.assertIn("OEBPS/Text/ch1.xhtml", paths)
        self.assertNotIn("ch1.xhtml", paths)

    def test_charoffset_is_absolute_rather_than_a_column(self):
        """Sigil scrolls to `charoffset` in preference to the line number, so
        a column here moves the cursor rather than mislabelling it."""
        for element in self.once.results:
            if element.get("linenumber") == "-1":
                continue
            line = int(element.get("linenumber"))
            offset = int(element.get("charoffset"))
            if line > 1:
                self.assertGreater(
                    offset, line,
                    "%s looks like a column, not an offset"
                    % element.get("message"))

    def test_the_summary_row_carries_a_space_and_not_an_empty_bookpath(self):
        """An empty `bookpath` is read by Sigil as a complaint about the
        plugin itself, so the row that belongs to no file gets a space."""
        # One parse, because `results` re-parses on every access and two
        # calls therefore hand back different objects for the same row.
        rows = self.once.results
        summary = [e for e in rows if e.get("linenumber") == "-1"]
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0].get("bookpath"), " ")
        self.assertEqual(summary[0].get("charoffset"), "-1")
        self.assertIn("epubveri", summary[0].get("message"))
        self.assertEqual(rows[-1].get("linenumber"), "-1",
                         "the summary belongs last, after the findings")

    def test_the_display_settings_are_written_on_the_first_run(self):
        for key in ("show_usage", "show_advisory", "show_summary", "sort"):
            self.assertIn(key, self.once.prefs)
        self.assertTrue(self.once.prefs["show_usage"])
        self.assertTrue(self.once.prefs["show_advisory"])
        self.assertTrue(self.once.prefs["show_summary"])

    def test_usage_and_advisory_findings_reach_sigil_by_default(self):
        """What 374286 #274 says in public — "there is nothing to switch on".

        `-u` and `--advisory` are passed on every run and the settings filter
        the *display*, so both categories are visible without the user
        finding anything.
        """
        codes = _codes(self.once)
        self.assertIn("USAGE OPF-097", codes)
        self.assertIn("ADVISORY ADV-001", codes)


@unittest.skipIf(SKIP, SKIP or "")
class SortOrderTests(unittest.TestCase):
    """The three orders, each through the launcher rather than through us.

    `test_plugin.py` already pins the ordering function. What it cannot see is
    that Sigil keeps the order it is given — it has a sortable results table
    of its own, and a plugin that assumed otherwise would look correct in
    every unit test and wrong on screen.
    """

    def test_severest_first_is_the_default(self):
        self.assertEqual(
            _codes(run_in_sigil("severity")),
            ["ERROR RSC-005", "ERROR RSC-005", "USAGE OPF-097",
             "ADVISORY ADV-001"])

    def test_severity_low_reverses_it(self):
        self.assertEqual(
            _codes(run_in_sigil("severity-low")),
            ["ADVISORY ADV-001", "USAGE OPF-097", "ERROR RSC-005",
             "ERROR RSC-005"])

    def test_document_order_follows_the_book(self):
        """content.opf before ch1.xhtml, and within a file by position — so
        the advisory at offset 131 precedes the error at 168."""
        run = run_in_sigil("document")
        rows = [(e.get("bookpath"), int(e.get("charoffset")))
                for e in run.results if e.get("linenumber") != "-1"]
        # The book's order, not the alphabet's — `OEBPS/content.opf` comes
        # first here and sorts *after* `OEBPS/Text/ch1.xhtml`. A `sorted()`
        # check was written first and failed for exactly that reason.
        self.assertEqual([path for path, _ in rows],
                         ["OEBPS/content.opf", "OEBPS/content.opf",
                          "OEBPS/Text/ch1.xhtml", "OEBPS/Text/ch1.xhtml"])
        for name in ("OEBPS/content.opf", "OEBPS/Text/ch1.xhtml"):
            within = [off for path, off in rows if path == name]
            self.assertEqual(within, sorted(within))
        self.assertEqual(
            _codes(run),
            ["ERROR RSC-005", "USAGE OPF-097", "ADVISORY ADV-001",
             "ERROR RSC-005"])


if __name__ == "__main__":
    if SKIP:
        print("skipped: %s" % SKIP)
    unittest.main(verbosity=2)
