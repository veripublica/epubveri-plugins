# epubveri for calibre — this plugin's client for the epubveri binary
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""This plugin's client for the epubveri binary.

**It belongs to the calibre plugin and to nothing else.** The Sigil plugin has
its own copy: they are applications for different programs that happen to share
a language, and someone auditing one of them should read one folder. The two
copies will not stay identical for long either — this one has calibre's
`JSONConfig` for preferences, `iswindows` for platform tests and calibre's own
plugin-directory conventions to use, where the Sigil one has Sigil's `bk`.

Talks to epubveri as a subprocess over its documented JSON envelope and never
links it, so a GPL-3 plugin package conveys no AGPL code; the binary is fetched
from epubveri's own releases on first use and verified against that release's
`SHA256SUMS.txt`.
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
