# epubveri-plugins — finding, fetching and verifying the epubveri binary
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Get a trustworthy epubveri binary onto the user's machine.

**No binary is shipped inside the plugin zip, and that is a licence decision
as much as a size one.** epubveri is AGPL-3.0-only OR commercial; this plugin
is GPL-3.0. Because the plugin only ever runs the binary as a subprocess and
never links it, and because the user's own machine fetches it from the
project's releases, a plugin package distributes no AGPL code at all and
carries none of the notice or source-offer obligations that would follow.
Putting the binary in the zip would change that on the day it happened.

**Every download is verified against `SHA256SUMS.txt`.** Releases have shipped
that file plus build provenance since 0.12.4, and neither third-party plugin
checked it — so the guarantee reached nobody. Verification here is the point of
the file existing.
"""

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import tarfile
import tempfile
import zipfile
from urllib.request import Request, urlopen

REPO = "veripublica/epubveri"
CHECKSUMS_NAME = "SHA256SUMS.txt"

#: GitHub serves the newest release's assets from a stable path, so nothing
#: here needs the API. That matters twice over: the API answers with **31 KB**
#: of JSON where `SHA256SUMS.txt` is **842 bytes**, and it is rate-limited for
#: unauthenticated callers where a release download is not.
LATEST_DOWNLOAD = "https://github.com/%s/releases/latest/download/%%s" % REPO

#: Every network call gets one. Neither third-party plugin set a timeout, so a
#: hung connection froze the editor with no way out; Python's default here is
#: "wait forever".
NETWORK_TIMEOUT = 30

#: Release assets are named `epubveri-<rust target triple>.<ext>`. The mapping
#: is exact, not fuzzy: a wrong guess downloads a binary that will not run, and
#: the failure surfaces much later as "epubveri is broken".
#:
#: `gnu` rather than `musl` for Linux is deliberate and is the opposite of what
#: epubveri's own USAGE.md used to advise: the musl builds are static and run
#: anywhere, which matters for a container, but a desktop editor is already on
#: a glibc system and the gnu build is the one its users expect.
_TARGETS = {
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Windows", "ARM64"): "aarch64-pc-windows-msvc",
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("Linux", "arm64"): "aarch64-unknown-linux-gnu",
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
}


class DownloadError(Exception):
    pass


def binary_filename():
    return "epubveri.exe" if platform.system() == "Windows" else "epubveri"


def target_triple():
    """The release target for this machine, or None if we do not build one."""
    system = platform.system()
    machine = platform.machine()
    triple = _TARGETS.get((system, machine))
    if triple is None and system == "Linux" and machine in ("i686", "i386"):
        return None  # 32-bit x86 is not built
    return triple


def asset_name(triple=None):
    triple = triple or target_triple()
    if triple is None:
        return None
    ext = ".zip" if "windows" in triple else ".tar.gz"
    return "epubveri-%s%s" % (triple, ext)


def _get(url, timeout=NETWORK_TIMEOUT):
    request = Request(url, headers={
        # GitHub asks for a User-Agent and answers 403 without one.
        "User-Agent": "epubveri-plugins",
        "Accept": "application/vnd.github+json",
    })
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def latest_checksums(timeout=NETWORK_TIMEOUT):
    """`{asset name: sha256}` for the newest release. 842 bytes.

    **This is the update check.** Comparing checksums rather than version
    numbers is smaller, needs no `epubveri -V` process, and is strictly more
    sensitive: it also catches an archive re-uploaded under the same tag, and a
    local copy that has been corrupted or replaced.
    """
    text = _get(LATEST_DOWNLOAD % CHECKSUMS_NAME, timeout).decode("utf-8",
                                                                 "replace")
    sums = {}
    for line in text.splitlines():
        match = re.match(r"^([0-9a-fA-F]{64})\s+\*?(\S+)\s*$", line)
        if match:
            sums[os.path.basename(match.group(2))] = match.group(1).lower()
    return sums


def _expected_sha256(checksums_text, name):
    """Pull one hash out of `SHA256SUMS.txt`.

    The file is `sha256sum` output: `<64 hex>  <name>`, one per line. Matching
    is on the exact asset name — a basename comparison would happily accept the
    hash of a different platform's archive.
    """
    for line in checksums_text.splitlines():
        match = re.match(r"^([0-9a-fA-F]{64})\s+\*?(\S+)\s*$", line)
        if match and os.path.basename(match.group(2)) == name:
            return match.group(1).lower()
    return None


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_version(text):
    """`"epubveri 0.13.3+353c51a"` or `"v0.13.3"` -> `(0, 13, 3)`.

    Build metadata after `+` is dropped: `0.13.3+353c51a` and `0.13.3` are the
    same release, and comparing the strings would call one an update of the
    other forever.
    """
    if not text:
        return None
    token = text.strip().split()[-1].lstrip("vV").split("+")[0]
    parts = token.split(".")
    try:
        return tuple(int(p) for p in parts[:3])
    except ValueError:
        return None


def download_binary(destdir, expected=None, timeout=NETWORK_TIMEOUT):
    """Fetch the newest archive, verify it, extract the binary into `destdir`.

    Returns `(path, sha256)`. The hash is what the caller stores: the next
    check is a string comparison against 842 bytes rather than a download.

    Raises `DownloadError` with a sentence fit to show a user — the caller has
    no better information to add.
    """
    name = asset_name()
    if name is None:
        raise DownloadError(
            "no epubveri build for this platform (%s %s); it can be built from "
            "source, or run from a terminal instead"
            % (platform.system(), platform.machine()))

    if expected is None:
        sums = latest_checksums(timeout)
        expected = sums.get(name)
        if expected is None:
            raise DownloadError(
                "%s does not list %s — refusing to install an archive the "
                "release does not vouch for" % (CHECKSUMS_NAME, name))

    tmpdir = tempfile.mkdtemp(prefix="epubveri-dl-")
    try:
        archive = os.path.join(tmpdir, name)
        with open(archive, "wb") as handle:
            handle.write(_get(LATEST_DOWNLOAD % name, timeout))

        # Verified before it is ever extracted, let alone run. This is the
        # only reason a user can trust a binary that arrived over the network.
        actual = _sha256(archive)
        if actual != expected:
            raise DownloadError(
                "checksum mismatch for %s: the release lists %s and the "
                "downloaded file is %s. Nothing was installed."
                % (name, expected[:16], actual[:16]))

        binary = binary_filename()
        extracted = os.path.join(tmpdir, "x")
        os.makedirs(extracted)
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extracted)
        else:
            with tarfile.open(archive) as tf:
                tf.extractall(extracted)

        found = None
        for root, _dirs, files in os.walk(extracted):
            if binary in files:
                found = os.path.join(root, binary)
                break
        if found is None:
            raise DownloadError("%s contained no %s" % (name, binary))

        if not os.path.isdir(destdir):
            os.makedirs(destdir)
        target = os.path.join(destdir, binary)
        shutil.copy2(found, target)
        mode = os.stat(target).st_mode
        os.chmod(target, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return target, expected
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
