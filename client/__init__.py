# epubveri-plugins — shared client for the epubveri validator
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Everything the editor plugins share.

This package is **vendored**, not installed: a Sigil plugin is a flat folder
and a calibre plugin is a zip, and neither can import a sibling package from
another directory. The build copies `client/` into each artefact, which is
also why nothing here may import from `sigil/` or `calibre/` — the dependency
runs one way only.

It talks to epubveri as a **subprocess over its documented JSON envelope**, and
never links it. That keeps the licences apart (epubveri is AGPL-3.0-only OR
commercial; these plugins are GPL-3.0) and it is why no epubveri binary is
shipped inside a plugin package: the user's machine fetches it from the
project's own releases.
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
