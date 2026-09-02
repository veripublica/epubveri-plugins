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

# **Every finding is shown, and there are no settings.** Sigil offers a plugin
# no configuration screen — Manage Plugins lists name, version, author, type,
# engine and platforms and nothing else — so a preference here would be a
# switch the user cannot reach.
#
# That constraint pushed the right way. On the command line `usage` findings
# and `--advisory` are off by default, because a script diffing epubveri
# against epubcheck has to see the same report from both. A results panel is
# not a diff: it has a Type column and every line here says what it is, so the
# reader gets everything, labelled, and judges for themselves.
#
# What does **not** change is the verdict. `ADV-*`/`NEXT-*` never move
# VALID/NOT VALID — epubveri's standing guarantee, measured across 444 books —
# so a book that passes epubcheck still passes here.


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


def _label(finding):
    """The word in front of a finding, so that no line can be mistaken for
    something epubcheck said."""
    return "ADVISORY" if finding.is_advisory else finding.severity.upper()


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


def _report(bk, envelope, workdir):
    """Put every finding into Sigil's validation panel."""
    shown = 0
    for finding in sorted(envelope.findings, key=lambda f: f.sort_key):
        text = "%s %s: %s" % (_label(finding), finding.code, finding.message)
        if finding.is_advisory:
            # Say plainly why this line is not in epubcheck's output.
            # Without it an advisory reads as the two tools disagreeing,
            # rather than as an extra opinion that moves no verdict.
            text += "  [epubcheck does not report this; the verdict is " \
                    "unaffected]"

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
            # `-u` and `--advisory` always; the panel shows everything.
            envelope = runner.run_epubveri(binary, epub_path)
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

        _report(bk, envelope, workdir)
        verdict = "VALID" if envelope.is_valid else "NOT VALID"
        # The verdict line quotes only errors and fatals, because that is what
        # decides it and what epubcheck would print. Usage notes and
        # advisories are in the panel above and count towards neither.
        summary = "epubveri %s — %s (%d error(s), %d warning(s))" % (
            envelope.version, verdict,
            envelope.count("error") + envelope.count("fatal"),
            envelope.count("warning"))
        advisory = sum(1 for f in envelope.findings if f.is_advisory)
        # `ADV-*`/`NEXT-*` are emitted AT usage severity, so the envelope's
        # usage count already contains them; subtract or they are counted
        # twice.
        usage = envelope.count("usage") - advisory
        extra = []
        if usage > 0:
            extra.append("%d usage note(s)" % usage)
        if advisory:
            extra.append("%d advisory finding(s) epubcheck does not make"
                         % advisory)
        if extra:
            summary += "; also listed: %s — neither affects the verdict" \
                       % ", ".join(extra)
        bk.add_result("info", "", -1, _xml_attr(summary))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return 0


def main():
    print("This is a Sigil plugin; run it from Sigil's Plugins menu.")
    return -1


if __name__ == "__main__":
    sys.exit(main())
