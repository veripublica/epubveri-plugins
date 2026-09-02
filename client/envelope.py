# epubveri-plugins — parsing epubveri's JSON envelope
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""The `--format json` envelope, read the way `docs/INTEGRATING.md` says to.

Four things in here exist because getting them wrong is what the audit of the
two third-party plugins found, and six of those nine findings were epubveri's
own documentation's fault rather than theirs:

  * **Parse stdout first, whatever the exit code.** Exit 2 has three shapes and
    only one of them answers on stderr. A missing file returns a full envelope
    with a `PKG-018` fatal and an *empty* stderr; so does an unnameable input,
    with `status: "error"`. A plugin that prints stderr on exit 2 shows its
    user a blank error in the two commonest cases.
  * **`status: "error"` is not "the file could not be read".** The line is
    whether the fault can be *named with a code*: a nameable fault is a verdict
    (`"problems"`, the finding in `items`, however severe). That is why a
    missing file is a PKG-018 and a directory is not.
  * **Message ids are not all `XXX-000`.** Seventeen of them use an underscore
    (`HTM_060b`, `MED_013`), and lettered suffixes are real and distinct. A
    regex of `[A-Z]+-[0-9]+` drops all seventeen silently, so nothing here
    parses an id — it is carried through as the string epubveri printed.
  * **`summary`'s keys are the severity words**, so `summary[severity]` is a
    direct lookup rather than something needing a mapping.
"""

import json

#: Worst first. A host with fewer levels collapses these but should keep the
#: original word in whatever it shows, because it is the word epubcheck uses.
SEVERITY_ORDER = {"fatal": 0, "error": 1, "warning": 2, "info": 3, "usage": 4}

#: What an advisory finding is grounded in. `spec-ahead` becomes an ordinary
#: error the day epubcheck implements it; `spec-silent` never does. Only
#: `ADV-*`/`NEXT-*` findings carry it, and only when `--advisory` was passed.
ADVISORY_BASIS = ("spec-ahead", "spec-silent")


class EnvelopeError(Exception):
    """stdout held no envelope at all — epubveri did not start, or the command
    line was wrong. This is the only case where stderr is the answer."""


class Finding:
    """One item out of `inputs[].items`.

    Attributes mirror the envelope's field names so that a reader can check
    them against `docs/INTEGRATING.md` without a translation table.
    """

    __slots__ = ("code", "rule", "severity", "location", "line", "column",
                 "message", "params", "element_path", "namespaces",
                 "advisory_basis", "violation_kind")

    def __init__(self, item):
        self.code = item.get("code", "")
        # epubveri's finer sub-code. Stable, and the thing to key on when a
        # single message id covers several conditions.
        self.rule = item.get("rule")
        self.severity = item.get("severity", "error")
        # A container-relative path such as "OEBPS/Text/ch1.xhtml" — a FULL
        # path, not a basename. Reducing it to a basename is how a plugin sends
        # the cursor to the wrong file when two folders hold the same name.
        self.location = item.get("location")
        pos = item.get("position") or {}
        self.line = pos.get("line")
        self.column = pos.get("column")
        self.message = item.get("message", "")
        data = item.get("data") or {}
        self.params = data.get("params") or []
        self.element_path = data.get("element_path")
        self.namespaces = data.get("namespaces") or {}
        self.advisory_basis = data.get("advisory_basis")
        self.violation_kind = data.get("violation_kind")

    @property
    def is_advisory(self):
        """True for `ADV-*`/`NEXT-*`. These never move the verdict or the exit
        code, so a host may present them differently — but it must not treat
        them as ordinary errors."""
        return self.advisory_basis in ADVISORY_BASIS

    @property
    def sort_key(self):
        return (SEVERITY_ORDER.get(self.severity, 9),
                self.location or "",
                self.line or 0,
                self.column or 0)

    def __repr__(self):
        where = self.location or "(no file)"
        if self.line:
            where += ":%s:%s" % (self.line, self.column)
        return "<Finding %s %s %s>" % (self.severity, self.code, where)


class Envelope:
    """One `--format json` run. `findings` is the first input's items, since
    the plugins validate one book at a time."""

    def __init__(self, doc):
        self.tool_version = doc.get("tool_version", "")
        # Envelope-level status. Per-input status is the one to act on.
        self.status = doc.get("status", "")
        inputs = doc.get("inputs") or [{}]
        book = inputs[0]
        self.input_status = book.get("status", "")
        # Set only when the fault could not be named with a code; `items` is
        # then empty and this holds the reason.
        self.error = book.get("error")
        self.summary = book.get("summary") or {}
        self.findings = [Finding(i) for i in (book.get("items") or [])]

    @property
    def version(self):
        """The version without build metadata: `0.13.3+353c51a` -> `0.13.3`."""
        return self.tool_version.split("+")[0]

    @property
    def is_valid(self):
        """Exactly: no error and no fatal. Not a quality score, and not
        affected by `--advisory`."""
        return self.input_status == "ok"

    @property
    def could_not_read(self):
        return self.input_status == "error"

    def count(self, severity):
        return self.summary.get(severity, 0)


def parse_envelope(stdout, stderr=b"", returncode=0):
    """Turn one epubveri run into an `Envelope`.

    `stdout` is decoded leniently on purpose: a book can carry any encoding in
    its own text, and a plugin that raises on a decode error tells its user
    nothing about the book.
    """
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    try:
        doc = json.loads(stdout)
    except ValueError:
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        raise EnvelopeError(
            stderr.strip()
            or "epubveri exited with %s and produced no output" % returncode
        )
    return Envelope(doc)
