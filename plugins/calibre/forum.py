#!/usr/bin/env python3
# epubveri for calibre's editor — stage the MobileRead attachment set
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Stage the two files to attach to the first post of MobileRead 375293.

    python3 plugins/calibre/forum.py
        -> dist/calibre/forum/epubveri_calibre_vX.Y.Z.zip
        -> dist/calibre/forum/SHA256SUMS.txt

**This attachment is not a convenience download.** This plugin is in calibre's
plugin index (verified 2026-09-17 in the live `plugins.json.bz2`:
`index_name: epubveri`, `thread_id: 375293`, ours by author), so the zip on
that first post is what every calibre in the world installs and updates from.
Getting it wrong is not a broken link; it is a broken install, everywhere.

**It stages the published release asset rather than a local build**, which is
the whole point: the README promises that the zip on a forum thread can be
checked against the source that produced it, and that only holds if the forum
carries the same bytes and the same checksum file as the release.

**How calibre's index reads a thread** (measured 2026-09-17 against
`setup/plugins_mirror.py`): it scrapes one index post for thread links, takes
the **first `.zip` attachment** on each thread page, and reads the version out
of the plugin class in `__init__.py` with an AST parse. Three consequences:

- the **filename reaches nobody** — calibre stores the download as
  `375293.zip` — so a versioned name is free, and `SHA256SUMS.txt` can name
  the file it actually sits beside;
- the **version users see is `PLUGIN_VERSION_TUPLE`** inside the zip, not the
  post text and not the archive name, so a release that forgets to bump it is
  invisible as an update;
- the **update trigger is the attachment's `Last-Modified`**, so replacing the
  attachment is the whole of the operation.

Its sibling, `plugins/calibre-library/forum.py`, does the same for the library
plugin, which has been in the index too since 2026-09-18.

This script does not touch the forum. Attaching is manual and stays that way.
"""

import hashlib
import os
import shutil
import sys
import urllib.error
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

sys.path.insert(0, HERE)
import build  # noqa: E402  (sibling module, not a package)

FORUM = os.path.join(build.DIST, "forum")

THREAD = "375293"
THREAD_URL = "https://www.mobileread.com/forums/showthread.php?t=" + THREAD

REPO = "veripublica/epubveri-plugins"
TAG_PREFIX = "calibre-v"
ASSET = "epubveri_calibre_v%s.zip"
SUMS = "SHA256SUMS.txt"

#: calibre will not import the plugin unless both of these are at the top of
#: the archive. A zip that is wrong here installs as nothing at all, and the
#: first person to find out is a user.
REQUIRED_AT_ROOT = ("__init__.py", "plugin-import-name-epubveri.txt")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(tag, name, target):
    url = "https://github.com/%s/releases/download/%s/%s" % (REPO, tag, name)
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise SystemExit(
                "%s is not on release %s.\nCut the release before staging the "
                "forum attachment — the thread must carry what GitHub serves."
                % (name, tag)
            )
        raise SystemExit("could not fetch %s: %s" % (url, err))
    with open(target, "wb") as handle:
        handle.write(data)
    return target


def checksum_for(sums_path, name):
    """The digest `SHA256SUMS.txt` records for `name`, or a hard failure."""
    with open(sums_path, encoding="utf-8") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                return parts[0]
    raise SystemExit(
        "%s does not name %s.\nA reader running `shasum -a 256 -c %s` beside "
        "the download would get 'no such file'." % (SUMS, name, SUMS)
    )


def check_archive(path, expected_version):
    """Refuse to stage an archive calibre could not install or would misread."""
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        missing = [n for n in REQUIRED_AT_ROOT if n not in names]
        if missing:
            raise SystemExit(
                "%s is missing %s at the root of the archive"
                % (os.path.basename(path), ", ".join(missing))
            )
        text = zf.read("__init__.py").decode("utf-8")
    match = build.VERSION_RE.search(text)
    got = [p.strip() for p in match.group(1).split(",")] if match else None
    if got != expected_version.split("."):
        raise SystemExit(
            "the released archive declares %s, this tree declares %s"
            % (".".join(got or ["?"]), expected_version)
        )


def drift_from_source(released):
    """Which members of the released archive this tree would build differently.

    The build is reproducible, so this is a real comparison rather than a
    timestamp artefact — it caught `forum.py` packaging itself into the plugin
    the first time it ran.

    **It is reported, not enforced, and the distinction is the point.** What
    belongs on the forum is the released artifact, which is what was
    downloaded and verified above; a tree that has moved on since the release
    does not make that artifact wrong. What drift means is that the *next*
    release will carry these files, so it is worth knowing whether they are a
    README or the client code before deciding to attach and walk away.
    """
    local = build.build()
    if sha256(local) == sha256(released):
        return []
    with zipfile.ZipFile(released) as a, zipfile.ZipFile(local) as b:
        names = sorted(set(a.namelist()) | set(b.namelist()))
        return [
            n for n in names
            if n not in a.namelist() or n not in b.namelist()
            or a.read(n) != b.read(n)
        ]


def stage():
    version = build.version()
    tag = TAG_PREFIX + version
    name = ASSET % version

    shutil.rmtree(FORUM, ignore_errors=True)
    os.makedirs(FORUM)

    archive = download(tag, name, os.path.join(FORUM, name))
    sums = download(tag, SUMS, os.path.join(FORUM, SUMS))

    digest = sha256(archive)
    recorded = checksum_for(sums, name)
    if digest != recorded:
        raise SystemExit(
            "the downloaded archive does not match %s on release %s\n"
            "  recorded  %s\n  actual    %s" % (SUMS, tag, recorded, digest)
        )

    check_archive(archive, version)
    drift = drift_from_source(archive)

    # The index takes the first zip it finds on the thread page, and the index
    # post's own instructions say not to attach more than one. Staging exactly
    # one removes the chance of uploading the wrong file from a folder that
    # keeps every build.
    zips = [f for f in os.listdir(FORUM) if f.endswith(".zip")]
    if len(zips) != 1:
        raise SystemExit("expected exactly one zip to attach, found %d" % len(zips))

    return version, tag, archive, sums, digest, drift


if __name__ == "__main__":
    version, tag, archive, sums, digest, drift = stage()
    rel = os.path.relpath(FORUM, ROOT)
    print("epubveri for calibre %s (%s) — verified against the release\n"
          % (version, tag))
    print("  %s/%s  (%.1f KB)" % (rel, os.path.basename(archive),
                                  os.path.getsize(archive) / 1024.0))
    print("  %s/%s" % (rel, os.path.basename(sums)))
    print("  sha256  %s\n" % digest)
    print("Attach both to the FIRST post of %s" % THREAD_URL)
    print("  1. delete the zip already attached there first — the index takes")
    print("     the first zip on the page, so a leftover old one wins forever")
    print("  2. upload these two, then check the post shows one zip only")
    print("  3. the index re-scrapes on its own schedule, not immediately")
    if drift:
        print("\nNote: this tree would build %d file(s) differently from the"
              % len(drift))
        print("release above. The attachment is still the released artifact and")
        print("is correct; these are what the next release will carry:")
        for name in drift:
            print("  - %s" % name)
    print("\nThis plugin IS in calibre's plugin index: every installed copy")
    print("updates from this attachment. Nothing else to notify.")
    sys.exit(0)
