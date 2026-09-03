# epubveri-plugins — shared client for the epubveri validator
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""This plugin's client for the epubveri binary.

**It belongs to the calibre plugin and to nothing else.** Every plugin in this
repository carries its own copy of whatever it needs, even when another plugin
is written in the same language, because they are applications for different
programs: someone auditing the calibre plugin should be able to read one folder
and be done. The calibre plugin will not share this code — it has calibre's
own `JSONConfig`, `iswindows` and plugin-directory conventions to use instead,
so a shared version would have to be either watered down or full of branches.

It talks to epubveri as a **subprocess over its documented JSON envelope**, and
never links it. That keeps the licences apart (epubveri is AGPL-3.0-only OR
commercial; this plugin is GPL-3.0) and it is why no epubveri binary is shipped
inside the plugin zip: the user's machine fetches it from the project's own
releases and verifies it.
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
