# epubveri-plugins — running the epubveri binary
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Invoke epubveri and hand back a parsed envelope.

`-u` is passed **always**, and that is a deliberate reversal of what the two
third-party plugins do. epubveri hides `usage` findings without it, exactly as
epubcheck does — but the flag belongs at the *display* layer, not at the fetch:
gating it here makes the summary counts describe the flag instead of the book,
and re-running the validator to change a display preference is a second
validation of the same file.
"""

import os
import subprocess

from .envelope import parse_envelope

#: A book that takes longer than this is not going to finish. epubveri does the
#: whole 444-book reference library in about 70 seconds, so a single book is
#: far under a second; the margin is for a pathological archive on a slow disk.
DEFAULT_TIMEOUT = 120


class EpubveriNotFound(Exception):
    """No usable binary. The caller offers to fetch one."""


def _no_window_kwargs():
    """Keep a console window from flashing on Windows.

    Worth the four lines: three quarters of epubveri's binary downloads are
    Windows, and a plugin that blinks a black box on every validation looks
    broken however correct its output is.
    """
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "startupinfo": startupinfo,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }


def run_epubveri(binary, epub_path, advisory=False, profile=None,
                 epub_version=None, timeout=DEFAULT_TIMEOUT):
    """Validate one packaged `.epub` and return an `Envelope`.

    Raises `EpubveriNotFound` if the binary is missing or not executable, and
    `EnvelopeError` if stdout held no envelope — which is the only situation
    where stderr carries the explanation.
    """
    if not binary or not os.path.isfile(binary):
        raise EpubveriNotFound(binary or "(no path)")

    cmd = [binary, "--format", "json", "-u", "-i", epub_path]
    if advisory:
        cmd.append("--advisory")
    if profile:
        cmd.extend(["--profile", profile])
    if epub_version:
        cmd.extend(["-v", epub_version])

    proc = subprocess.run(cmd, capture_output=True, timeout=timeout,
                          **_no_window_kwargs())
    # Parse stdout first, whatever the exit code: exit 2 still carries a full
    # envelope for a missing or unreadable file and stderr is empty there.
    return parse_envelope(proc.stdout, proc.stderr, proc.returncode)


def binary_version(binary, timeout=15):
    """`epubveri -V` output, or None. Used to decide whether to offer an
    update; never to decide whether the binary works."""
    try:
        proc = subprocess.run([binary, "-V"], capture_output=True,
                              timeout=timeout, **_no_window_kwargs())
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or b"").decode("utf-8", "replace").strip()
    return text or None
