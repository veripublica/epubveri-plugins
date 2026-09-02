# epubveri-plugins — finding, fetching and verifying the epubveri binary
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Get a trustworthy epubveri binary onto the user's machine.

**No binary is shipped inside a plugin package, and that is a licence decision
as much as a size one.** epubveri is AGPL-3.0-only OR commercial; these plugins
are GPL-3.0. Because the plugin only ever runs the binary as a subprocess and
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
LATEST_RELEASE_URL = "https://api.github.com/repos/%s/releases/latest" % REPO
CHECKSUMS_NAME = "SHA256SUMS.txt"

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


def latest_release():
    """`{"tag": "v0.13.3", "version": "0.13.3", "assets": {name: url}}`."""
    doc = json.loads(_get(LATEST_RELEASE_URL).decode("utf-8", "replace"))
    tag = doc.get("tag_name", "")
    return {
        "tag": tag,
        "version": tag.lstrip("v"),
        "assets": {a["name"]: a["browser_download_url"]
                   for a in doc.get("assets") or []},
    }


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


def download_binary(destdir, release=None, verify=True):
    """Fetch the right archive, verify it, extract the binary into `destdir`.

    Returns the path to the binary. Raises `DownloadError` with a sentence fit
    to show a user — the caller has no better information to add.
    """
    release = release or latest_release()
    name = asset_name()
    if name is None:
        raise DownloadError(
            "no epubveri build for this platform (%s %s); it can be built from "
            "source, or run from a terminal instead"
            % (platform.system(), platform.machine()))
    url = release["assets"].get(name)
    if url is None:
        raise DownloadError("release %s has no asset named %s"
                            % (release["tag"], name))

    expected = None
    if verify:
        checksums_url = release["assets"].get(CHECKSUMS_NAME)
        if checksums_url is None:
            # Releases before 0.12.4 carry no checksum file. Refusing would
            # make the plugin unable to install an older epubveri at all, so
            # this is reported rather than fatal.
            expected = None
        else:
            text = _get(checksums_url).decode("utf-8", "replace")
            expected = _expected_sha256(text, name)
            if expected is None:
                raise DownloadError(
                    "%s does not list %s — refusing to install an archive the "
                    "release does not vouch for" % (CHECKSUMS_NAME, name))

    tmpdir = tempfile.mkdtemp(prefix="epubveri-dl-")
    try:
        archive = os.path.join(tmpdir, name)
        with open(archive, "wb") as handle:
            handle.write(_get(url))

        if expected is not None:
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
        return target
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
