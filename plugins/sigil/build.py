#!/usr/bin/env python3
# epubveri for Sigil — package this plugin
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Zip this folder the way Sigil installs it.

Each plugin packages itself. A central build script would have to know every
editor's packaging quirks — **Sigil wants the plugin folder at the top level
of the zip and calibre wants the files themselves**, and getting it wrong is
not subtle: the editor simply refuses to install. That knowledge belongs to
the plugin, and a shared script would accumulate one branch per editor and
would also be the wrong language the day a plugin is not written in Python.

Sigil installs from a zip and never from a folder — its dialog is titled
"Select Plugin Zip Archive" and filters on `Plugin Files (*.zip)` — which is
why this step exists.

    python3 plugins/sigil/build.py            -> dist/sigil_epubveri_vX.Y.Z.zip
"""

import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DIST = os.path.join(ROOT, "dist")

#: Sigil reads the version from plugin.xml, so that is where it lives. A
#: version file of our own would be a second place that could disagree.
VERSION_RE = re.compile(r"<version>([^<]+)</version>")

#: What never goes to a user.
EXCLUDE = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "build.py",
                                 "epubveri", "epubveri.exe", ".DS_Store")


def version():
    text = open(os.path.join(HERE, "plugin.xml"), encoding="utf-8").read()
    match = VERSION_RE.search(text)
    if not match:
        raise SystemExit("plugin.xml has no <version>")
    return match.group(1).strip()


def build():
    staging = os.path.join(DIST, "sigil-staging")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(HERE, staging, ignore=EXCLUDE)
    # GPL-3 §4: the licence travels with the thing that is conveyed.
    shutil.copy2(os.path.join(ROOT, "LICENSE"), staging)

    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, "sigil_epubveri_v%s.zip" % version())
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirs, files in os.walk(staging):
            for name in sorted(files):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, staging).replace(os.sep, "/")
                # Sigil expects one top-level folder, named for the plugin.
                zf.write(full, "epubveri/%s" % rel)
    shutil.rmtree(staging, ignore_errors=True)
    return out


if __name__ == "__main__":
    path = build()
    print("%s  (%.1f KB)" % (os.path.relpath(path, ROOT),
                             os.path.getsize(path) / 1024.0))
    sys.exit(0)
