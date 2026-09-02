#!/usr/bin/env python3
# epubveri for Sigil — validate the current book with epubveri
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
#
# Sigil's plugin interface (`launcher.py`, `bookcontainer.py`,
# `validationcontainer.py`) is BSD-licensed by Kevin B. Hendricks, Doug Massay
# and John Schember, and this plugin imports none of it — `bk` arrives as an
# argument. So nothing here is a derivative of Sigil, and the GPL-3 above is a
# choice rather than an obligation.

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client import binary as bin_mod          # noqa: E402
from client import runner                     # noqa: E402
from client.envelope import EnvelopeError     # noqa: E402

# epubveri has five severities and Sigil's results panel has three. Collapse,
# but keep epubveri's own word at the front of the message: it is epubcheck's
# vocabulary and the thing a user will search for or quote in a bug report.
_SIGIL_TYPE = {
    "fatal": "error",
    "error": "error",
    "warning": "warning",
    "info": "info",
    "usage": "info",
}

# Defaults deliberately match epubveri's own CLI rather than overriding it:
# `usage` hidden (as epubcheck hides it without `-u`) and `--advisory` off
# (the family is opt-in by design and never moves the verdict). What the two
# third-party plugins got wrong was not the default but that nothing told the
# user a switch existed — so both live in prefs and both are named in the
# summary line of every run.
_DEFAULTS = {
    "show_usage": False,
    "advisory": False,
}


def _xml_attr(value):
    """Escape a string for a double-quoted XML attribute.

    **Sigil does not do this for us, and the omission is not obvious.** Its
    launcher builds the results document by raw interpolation:

        '<validationresult type="%s" bookpath="%s" ... message="%s" />'
            % (vres.restype, vres.bookpath, ..., vres.message)

    The same file has an `escapeit()` helper and uses it for the plugin's
    success message and error log, but not for this line. So a message
    containing a double quote closes the attribute early and Sigil answers
    "Error Parsing Result XML" — with no finding shown at all, and nothing to
    say which of them did it.

    epubveri's messages are full of them: it quotes element and attribute
    names the way epubcheck does. On one real book, 39 of 257 findings carried
    a `"`.

    Single quotes are left alone: they are legal inside a double-quoted
    attribute, and 247 of those 257 messages contain one.
    """
    return (value.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
                 .replace('"', "&quot;"))


def _prefs(bk):
    prefs = bk.getPrefs()
    for key, value in _DEFAULTS.items():
        prefs.setdefault(key, value)
    return prefs


def _plugin_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _binary_path():
    return os.path.join(_plugin_dir(), bin_mod.binary_filename())


def _build_epub(bk, destdir):
    """Write the book Sigil currently holds to a real `.epub` file.

    epubveri takes a packaged file and not an unpacked directory — a decided
    scope, so that every tool in this family hands the others the same unit.
    `copy_book_contents_to` gives the whole container including `mimetype` and
    `META-INF/`, and the OPF is then overwritten with Sigil's live one so that
    unsaved manifest or spine edits are what gets validated.
    """
    workdir = os.path.join(destdir, "book")
    os.makedirs(workdir)
    bk.copy_book_contents_to(workdir)

    opf_path = os.path.join(workdir, bk.get_opfbookpath())
    opf = bk.get_opf()
    if opf:
        with open(opf_path, "wb") as handle:
            handle.write(opf.encode("utf-8") if isinstance(opf, str) else opf)

    epub_path = os.path.join(destdir, "current.epub")
    # `mimetype` first and stored, which OCF requires and which epubveri checks
    # (PKG-006/PKG-007); zipping it deflated would make every run report a
    # packaging error the book does not have.
    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        mimetype = os.path.join(workdir, "mimetype")
        if os.path.isfile(mimetype):
            zf.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
        else:
            zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                        compress_type=zipfile.ZIP_STORED)
        for root, _dirs, files in os.walk(workdir):
            for name in sorted(files):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, workdir).replace(os.sep, "/")
                if rel == "mimetype":
                    continue
                zf.write(full, rel)
    return epub_path, workdir


def _line_offsets(text):
    """Character offset of the start of each 1-based line."""
    offsets = [0]
    for line in text.splitlines(True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _char_offset(workdir, location, line, column):
    """The absolute character offset of a finding, for Sigil's results panel.

    Sigil uses this **in preference to the line number** — `OpenResource`
    takes it as `position_to_scroll_to`, a Qt document position — so it has to
    be an offset from the start of the file rather than a column within the
    line, and an error here moves the cursor rather than merely mislabelling
    it.

    `_line_offsets` is 0-based (`offsets[0]` is where line 1 starts) and
    epubveri's line numbers are 1-based, so line N starts at `offsets[N - 1]`.
    Indexing it directly with the line number put every finding one line late:
    reported 283, highlighted 284. Only running it in Sigil could show that —
    the test that existed checked `_line_offsets` alone and passed throughout.
    """
    if not location or not line or line < 1:
        return None
    path = os.path.join(workdir, location.replace("/", os.sep))
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return None
    offsets = _line_offsets(text)
    if line > len(offsets):
        return None
    return offsets[line - 1] + max((column or 1) - 1, 0)


def _report(bk, envelope, workdir, prefs):
    shown = 0
    for finding in sorted(envelope.findings, key=lambda f: f.sort_key):
        if finding.is_advisory and not prefs["advisory"]:
            continue
        if finding.severity == "usage" and not finding.is_advisory \
                and not prefs["show_usage"]:
            continue

        text = "%s %s: %s" % (finding.severity.upper(), finding.code,
                              finding.message)
        if finding.is_advisory:
            text += "  [advisory: %s]" % finding.advisory_basis

        restype = _SIGIL_TYPE.get(finding.severity, "info")
        # `location` is a full container-relative path and Sigil wants exactly
        # that as the bookpath. Reducing it to a basename is how a plugin sends
        # the cursor into the wrong file when two folders hold the same name.
        bookpath = finding.location or ""
        line = finding.line or -1
        offset = _char_offset(workdir, finding.location,
                              finding.line, finding.column)
        if offset is None:
            bk.add_result(restype, _xml_attr(bookpath), line, _xml_attr(text))
        else:
            bk.add_extended_result(restype, _xml_attr(bookpath), line, offset,
                                   _xml_attr(text))
        shown += 1
    return shown


def run(bk):
    import shutil
    import tempfile

    prefs = _prefs(bk)
    binary = _binary_path()

    if not os.path.isfile(binary):
        try:
            binary = bin_mod.download_binary(_plugin_dir())
        except Exception as exc:                       # noqa: BLE001
            bk.add_result("error", "", -1, _xml_attr(
                "epubveri could not be installed: %s" % exc))
            return -1

    tmpdir = tempfile.mkdtemp(prefix="epubveri-sigil-")
    try:
        epub_path, workdir = _build_epub(bk, tmpdir)
        try:
            envelope = runner.run_epubveri(
                binary, epub_path, advisory=prefs["advisory"])
        except EnvelopeError as exc:
            bk.add_result("error", "", -1, _xml_attr("epubveri: %s" % exc))
            return -1
        except Exception as exc:                       # noqa: BLE001
            bk.add_result("error", "", -1,
                          _xml_attr("epubveri failed to run: %s" % exc))
            return -1

        if envelope.could_not_read:
            bk.add_result("error", "", -1, _xml_attr(
                "epubveri could not read the book: %s"
                % (envelope.error or "no reason given")))
            return -1

        shown = _report(bk, envelope, workdir, prefs)
        verdict = "VALID" if envelope.is_valid else "NOT VALID"
        hidden = len(envelope.findings) - shown
        summary = "epubveri %s — %s (%d error(s), %d warning(s))" % (
            envelope.version, verdict,
            envelope.count("error") + envelope.count("fatal"),
            envelope.count("warning"))
        if hidden:
            summary += "; %d hidden — see the plugin's preferences for " \
                       "usage notes and advisory checks" % hidden
        bk.add_result("info", "", -1, _xml_attr(summary))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        bk.savePrefs(prefs)
    return 0


def main():
    print("This is a Sigil plugin; run it from Sigil's Plugins menu.")
    return -1


if __name__ == "__main__":
    sys.exit(main())
