#!/usr/bin/env python3
# epubveri-plugins — build the installable plugin packages
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Produce one installable zip per editor, into `dist/`.

**Each plugin folder is already the whole plugin**, so this only packages: it
copies the folder plus the licence into a zip laid out the way the editor
expects. Nothing is generated and nothing is shared between plugins — they are
applications for different programs and each carries its own code, so that a
reader auditing one of them reads one folder.

Both editors install from a zip and never from a folder (Sigil's dialog is
titled "Select Plugin Zip Archive" and filters on `Plugin Files (*.zip)`;
calibre's "Load plugin from file" is the same), which is why this step exists
at all.

No epubveri binary is packaged. The plugin fetches one from the project's own
releases and verifies it against `SHA256SUMS.txt`, which keeps an AGPL binary
out of a GPL-3 package and keeps the download provenance visible to the user.
"""

import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")

#: plugin name -> its folder. Adding an editor is adding a line and a folder;
#: nothing else in this file knows anything about a particular plugin.
PACKAGES = {
    "sigil": "sigil",
}


def _plugin_version(srcdir):
    """Read the version out of the editor's own manifest, so there is exactly
    one place to bump it and it is the place the editor reads."""
    manifest = os.path.join(srcdir, "plugin.xml")
    if os.path.isfile(manifest):
        import re
        text = open(manifest, encoding="utf-8").read()
        match = re.search(r"<version>([^<]+)</version>", text)
        if match:
            return match.group(1).strip()
    return "0.0.0"


def build(name):
    srcdir = os.path.join(ROOT, PACKAGES[name])
    version = _plugin_version(srcdir)
    staging = os.path.join(DIST, "%s-staging" % name)
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)

    # The plugin folder as it stands, minus build and test residue.
    shutil.copytree(srcdir, staging,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                  "epubveri", "epubveri.exe",
                                                  "tests"),
                    dirs_exist_ok=True)
    # GPL-3 §4: keep the licence with the thing that is conveyed.
    shutil.copy2(os.path.join(ROOT, "LICENSE"), staging)

    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, "%s_epubveri_v%s.zip" % (name, version))
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirs, files in os.walk(staging):
            for filename in sorted(files):
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, staging).replace(os.sep, "/")
                # Sigil installs a plugin from a zip whose top level is the
                # plugin folder itself.
                zf.write(full, "%s/%s" % ("epubveri", rel))
    shutil.rmtree(staging, ignore_errors=True)
    return out


def main(argv):
    names = argv[1:] or sorted(PACKAGES)
    for name in names:
        if name not in PACKAGES:
            print("unknown package: %s (have: %s)"
                  % (name, ", ".join(sorted(PACKAGES))))
            return 2
        path = build(name)
        size = os.path.getsize(path)
        print("%s  (%.1f KB)" % (os.path.relpath(path, ROOT), size / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
