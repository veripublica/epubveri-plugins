# epubveri-plugins — shared client for the epubveri validator
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""This plugin's client for the epubveri binary.

**It belongs to the calibre library plugin and to nothing else.** Every plugin
in this repository carries its own copy of whatever it needs, even when another
plugin is written in the same language, because they are applications for
different programs: someone auditing one plugin should be able to read one
folder and be done.

The editor plugin beside it carries these same three modules, and that is the
convention rather than an oversight. The two are installed separately, a user
may have either one alone, and **they share nothing at all — not even the
validator binary**; `install.py` says why, and the short version is that a
library scan holds the binary open for ten minutes and Windows will not let
anything overwrite a running executable.

It talks to epubveri as a **subprocess over its documented JSON envelope**, and
never links it. That keeps the licences apart (epubveri is AGPL-3.0-only OR
commercial; this plugin is GPL-3.0-only) and it is why no epubveri binary is
shipped inside the plugin zip: the user's machine fetches it from the
project's own releases and verifies it.
"""

from .envelope import Finding, Envelope, parse_envelope, EnvelopeError
from .runner import run_epubveri, EpubveriNotFound

__all__ = [
    "Finding",
    "Envelope",
    "parse_envelope",
    "EnvelopeError",
    "run_epubveri",
    "EpubveriNotFound",
]
