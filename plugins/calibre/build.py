#!/usr/bin/env python3
# epubveri for calibre — package this plugin
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Zip this folder the way calibre installs it.

Each plugin packages itself; see the note in the Sigil plugin's `build.py` for
why. The difference that matters here: **calibre wants the plugin's files at
the top level of the zip**, where Sigil wants a folder. `__init__.py` and
`plugin-import-name-epubveri.txt` have to be at the root of the archive or
calibre will not import the plugin at all.

    python3 plugins/calibre/build.py    -> dist/calibre_epubveri_vX.Y.Z.zip
"""

import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DIST = os.path.join(ROOT, "dist")

#: calibre reads the version off the plugin class, so that is where it lives.
VERSION_RE = re.compile(r"PLUGIN_VERSION_TUPLE\s*=\s*\(([^)]*)\)")

EXCLUDE = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "build.py",
                                 "epubveri", "epubveri.exe", ".DS_Store")


def version():
    text = open(os.path.join(HERE, "__init__.py"), encoding="utf-8").read()
    match = VERSION_RE.search(text)
    if not match:
        raise SystemExit("__init__.py has no PLUGIN_VERSION_TUPLE")
    parts = [p.strip() for p in match.group(1).split(",") if p.strip()]
    return ".".join(parts)


def build():
    staging = os.path.join(DIST, "calibre-staging")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(HERE, staging, ignore=EXCLUDE)
    shutil.copy2(os.path.join(ROOT, "LICENSE"), staging)

    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, "calibre_epubveri_v%s.zip" % version())
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirs, files in os.walk(staging):
            for name in sorted(files):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, staging).replace(os.sep, "/")
                # No wrapping folder: calibre reads __init__.py from the top.
                zf.write(full, rel)
    shutil.rmtree(staging, ignore_errors=True)
    return out


if __name__ == "__main__":
    path = build()
    print("%s  (%.1f KB)" % (os.path.relpath(path, ROOT),
                             os.path.getsize(path) / 1024.0))
    sys.exit(0)
