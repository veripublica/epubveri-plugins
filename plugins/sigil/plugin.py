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
from datetime import datetime, timedelta, timezone

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

# A result that is about the book as a whole has no file, and **the empty
# string is not how you say so**. Sigil's result table resolves the bookpath
# to a resource and, when that fails, prints "*** Invalid Book Path Provided
# ***" for an empty one and the string itself for anything else
# (`ValidationResultsView::DisplayResults`). A single space is neither empty
# nor a path, so the File column comes out blank, which is what a summary line
# wants. Nothing trims it on the way: the launcher interpolates the attribute
# and XML attribute-value normalization leaves a space alone.
#
# Reported by DNSB on Windows (MobileRead 374939 #16), on the summary line.
# The same empty string was in seven other places, including every finding
# epubveri reports about the container rather than a file.
_NO_FILE = " "

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


#: How often to look for a newer epubveri.
#:
#: **One hour, not one day, because the check now costs 842 bytes.** It reads
#: the release's `SHA256SUMS.txt` and compares one line with the hash it stored
#: when it installed — no GitHub API (31 KB of JSON, and rate-limited), no
#: `epubveri -V` process. Comparing hashes is also stricter than comparing
#: version numbers: it notices an archive re-uploaded under the same tag, and a
#: local copy that has been corrupted or replaced.
#:
#: **Not on every run**, and that is the one thing worth arguing about. A
#: validation answers in well under a second; putting a network round trip in
#: front of every one of them means that on a bad link every book waits for the
#: timeout. An hour is short enough that a fix shipped this morning reaches the
#: user this morning.
_UPDATE_INTERVAL = timedelta(hours=1)

#: After this long without a *successful* check, say so once in the summary.
#: Not a warning and not an error - the validator works. But a copy this old
#: may report something that has since been fixed, and that is worth knowing
#: when a finding looks wrong. Thirty days, so a fortnight offline says
#: nothing.
_STALE_AFTER = timedelta(days=30)

#: The check gets a short one of its own. It is optional work, so it must fail
#: fast; the download that follows keeps the longer default because it is not.
_CHECK_TIMEOUT = 5


#: The preference key, and it is **written into the file with its default** on
#: the first run rather than only being read.
#:
#: Sigil gives a plugin no settings screen, so the JSON at
#: `plugins_prefs/epubveri/epubveri.json` is the only place to change this. A
#: key that is merely *honoured* would be invisible there — someone opening the
#: file would see no sign that the choice exists. Writing it means the file
#: documents itself.
#:
#: **What it governs is the network, not the version.** Someone who sets it to
#: "no" is saying "do not use my connection" — a metered link, an air-gapped
#: machine, or preference — not "keep me on an old validator", which nobody
#: wants from a tool whose releases are mostly fixes for wrong errors. So the
#: age line below still appears.
_UPDATE_KEY = "autoupdate"
_UPDATE_DEFAULT = True

#: The key is a JSON boolean, so the file reads `"autoupdate": true` and the
#: change is `false`. Strings are still accepted, because a hand-edited file
#: gets hand-typed values: someone may well write `"false"`, or `False`.
#:
#: The values that mean yes. **Everything else means no**, and the direction
#: matters more than the list.
#:
#: This is a value typed by hand into a text file, so it will not always be one
#: of ours: `no`, `hayır`, `nein`, `off`, or a typo. Listing what counts as
#: *off* would treat every one of those as consent and keep using someone's
#: connection against their wishes — the worst thing this switch can do.
#: Listing what counts as *on* fails the other way: an unrecognised value stops
#: the network, which is recoverable, visible in the report after a month, and
#: never worse than the user asked for.
_ON_VALUES = frozenset(["yes", "true", "on", "1", "y"])


def _updates_allowed(bk, prefs):
    value = prefs.get(_UPDATE_KEY)
    if value is None:
        # First run: write the default so the file shows the choice exists.
        prefs[_UPDATE_KEY] = _UPDATE_DEFAULT
        bk.savePrefs(prefs)
        return True
    if isinstance(value, bool):
        return value                      # calibre's checkbox writes a boolean
    return str(value).strip().lower() in _ON_VALUES


def _now():
    """UTC, timezone-aware. `datetime.utcnow()` is deprecated in the Python
    Sigil bundles (3.14) and is scheduled for removal."""
    return datetime.now(timezone.utc)


def _since(stamp):
    """How long ago `stamp` was, or None if it is missing or unreadable.

    Stamps written before this was timezone-aware are naive; they are read as
    UTC rather than discarded, so an upgrade does not force a check.
    """
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return _now() - when


def _stale_note(prefs, allowed=True):
    """One quiet line when the binary has not been checked for a long time.

    A user working offline is not missing anything and should not be told
    about the network — measured over 144 runs across three days, the plugin
    says nothing at all. But after a month the copy in use may report
    something that has since been fixed, and then "this is old" is the
    explanation for a finding that looks wrong. It is information, not a
    warning: no error, no verdict change, and nothing to do until there is a
    connection.
    """
    age = _since(prefs.get("last_update_success"))
    if age is None or age < _STALE_AFTER:
        return None
    if not allowed:
        return "this epubveri is %d days old; update checks are off" % age.days
    return ("this epubveri is %d days old and could not be checked for "
            "updates" % age.days)


def _integrity_failure(path, prefs):
    """Is the binary on disk still the one whose checksum the release vouched
    for? Returns a sentence when it is not, otherwise None.

    **Verifying at download time only proves what arrived, not what runs.**
    Between the two sits everything that can touch a file: a bad sync, a
    partial disk write, another program, or something worse. The hash of the
    2.8 MB binary costs 1.8 ms, which is under one percent of a validation, so
    there is no reason to trust yesterday's answer.

    A missing stored hash is not a failure — it means the plugin was upgraded
    from a version that did not record one. That is trusted once and recorded,
    rather than refusing to run a binary that is very probably fine.
    """
    stored = prefs.get("binary_sha256")
    actual = bin_mod.sha256_of(path)
    if not stored:
        prefs["binary_sha256"] = actual          # trust once, verify after
        return None
    if actual == stored:
        return None
    return ("the epubveri binary has changed since it was verified "
            "(expected %s, found %s). It was not run. Delete it from the "
            "plugin folder and validate again to reinstall a verified copy."
            % (stored[:16], actual[:16]))


def _install_failure(exc):
    """A sentence a Sigil user can act on.

    The raw exception is developer text — "<urlopen error [Errno 8] nodename
    nor servname provided, or not known>" tells someone validating a book
    nothing they can do. Our own `DownloadError` messages are already written
    for a reader (no build for this platform, checksum mismatch), so those pass
    through; anything else is treated as the network, which is what it almost
    always is.

    The detail stays, in parentheses, for whoever does want it.
    """
    if isinstance(exc, bin_mod.DownloadError):
        return "epubveri could not be installed: %s" % exc
    return ("epubveri could not be downloaded. The first run needs an "
            "internet connection; after that the plugin works offline. (%s)"
            % exc)


def _ensure_binary(bk):
    """The epubveri binary to use, installing or updating it as needed.

    Returns `(path, note)`; `note` is a sentence for the summary line, or None.

    **Updates are silent and automatic, and there is no prompt because there is
    nowhere to put one** — Sigil gives a plugin no settings screen and a
    validation run must not open dialogs. What makes that acceptable rather
    than presumptuous: nothing is run before its checksum matches what the
    release publishes, and the only thing a newer epubveri does is be right
    more often.

    **Nothing here may stop a validation.** A failed check leaves the binary
    that is already there and records the attempt, so a machine with no network
    makes one failed request an hour rather than one per book.
    """
    path = _binary_path()
    prefs = bk.getPrefs()

    def remember(archive_sha, binary_sha):
        prefs["installed_sha256"] = archive_sha
        prefs["binary_sha256"] = binary_sha
        prefs["last_update_check"] = _now().isoformat()
        prefs["last_update_success"] = prefs["last_update_check"]
        bk.savePrefs(prefs)

    if not os.path.isfile(path):
        installed, archive_sha, binary_sha = bin_mod.download_binary(_plugin_dir())
        remember(archive_sha, binary_sha)
        return installed, "installed epubveri"

    tampered = _integrity_failure(path, prefs)
    if tampered:
        return None, tampered

    if not _updates_allowed(bk, prefs):
        # Chosen, so nothing is attempted and nothing is said about it. The
        # age line still applies: it is about the report, not the network.
        return path, _stale_note(prefs, allowed=False)

    age = _since(prefs.get("last_update_check"))
    if age is not None and age < _UPDATE_INTERVAL:
        return path, None

    prefs["last_update_check"] = _now().isoformat()
    bk.savePrefs(prefs)
    try:
        sums = bin_mod.latest_checksums(timeout=_CHECK_TIMEOUT)
        wanted = sums.get(bin_mod.asset_name())
        prefs["last_update_success"] = prefs["last_update_check"]
        bk.savePrefs(prefs)
        if wanted and wanted != prefs.get("installed_sha256"):
            before = runner.binary_version(path) or ""
            _p, archive_sha, binary_sha = bin_mod.download_binary(
                _plugin_dir(), expected=wanted)
            remember(archive_sha, binary_sha)
            after = runner.binary_version(path) or ""
            return path, _update_note(before, after)
    except Exception:                                  # noqa: BLE001
        # Offline, rate-limited, a changed release layout - none of it is a
        # reason to refuse to validate the book in front of us.
        pass
    return path, _stale_note(prefs)


def _update_note(before, after):
    """"updated epubveri 0.13.3 to 0.13.4", or something honest if either
    version could not be read."""
    old = bin_mod.parse_version(before)
    new = bin_mod.parse_version(after)
    fmt = lambda v: ".".join(str(n) for n in v) if v else None
    if old and new and old != new:
        return "updated epubveri %s to %s" % (fmt(old), fmt(new))
    if new:
        return "reinstalled epubveri %s" % fmt(new)
    return "updated epubveri"


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
        bookpath = finding.location or _NO_FILE
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

    try:
        binary, update_note = _ensure_binary(bk)
    except Exception as exc:                           # noqa: BLE001
        bk.add_result("error", _NO_FILE, -1, _xml_attr(_install_failure(exc)))
        return -1

    if binary is None:
        # Integrity check failed. Nothing is executed.
        bk.add_result("error", _NO_FILE, -1,
                      _xml_attr("epubveri: %s" % update_note))
        return -1

    tmpdir = tempfile.mkdtemp(prefix="epubveri-sigil-")
    try:
        epub_path, workdir = _build_epub(bk, tmpdir)
        try:
            # `-u` and `--advisory` always; the panel shows everything.
            envelope = runner.run_epubveri(binary, epub_path)
        except EnvelopeError as exc:
            bk.add_result("error", _NO_FILE, -1,
                          _xml_attr("epubveri: %s" % exc))
            return -1
        except Exception as exc:                       # noqa: BLE001
            bk.add_result("error", _NO_FILE, -1,
                          _xml_attr("epubveri failed to run: %s" % exc))
            return -1

        if envelope.could_not_read:
            bk.add_result("error", _NO_FILE, -1, _xml_attr(
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
        if update_note:
            summary += " [%s]" % update_note
        bk.add_result("info", _NO_FILE, -1, _xml_attr(summary))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return 0


def main():
    print("This is a Sigil plugin; run it from Sigil's Plugins menu.")
    return -1


if __name__ == "__main__":
    sys.exit(main())
