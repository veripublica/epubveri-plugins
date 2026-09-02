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

**The zip's filename decides the folder name inside it, and a mismatch is
rejected outright** with "Error: Plugin not a valid Sigil plugin". From
`PluginDB::add_plugin` in Sigil's own source:

    QString name = zipinfo.baseName();       // "epubveri_v0.1.0"
    int version_index = name.indexOf("_");   // everything after the FIRST "_"
    name.truncate(version_index);            // ...is version, so name = "epubveri"

and then `verify_plugin_zip` requires *every* entry in the archive to begin
`epubveri/`, and `epubveri/plugin.xml` to be among them. So the archive must be
`<plugin folder name>_<anything>.zip`. Naming it `sigil_epubveri_v0.1.0.zip`
made Sigil look for a folder called `sigil` and refuse the plugin; the tests
now pin the rule.

    python3 plugins/sigil/build.py       -> dist/sigil/epubveri_vX.Y.Z.zip
"""

import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
#: Per-plugin, because the zip's *name* is part of Sigil's contract and both
#: plugins want to be called `epubveri`.
DIST = os.path.join(ROOT, "dist", "sigil")

#: The folder Sigil will create under its plugins directory. It must equal the
#: zip's basename up to the first underscore, and it is what the user sees in
#: Manage Plugins.
FOLDER = "epubveri"

#: Sigil reads the version from plugin.xml, so that is where it lives. A
#: version file of our own would be a second place that could disagree.
VERSION_RE = re.compile(r"<version>([^<]+)</version>")

#: What never goes to a user.
EXCLUDE = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "build.py",
                                 "epubveri", "epubveri.exe", ".DS_Store")


def version():
    with open(os.path.join(HERE, "plugin.xml"), encoding="utf-8") as handle:
        text = handle.read()
    match = VERSION_RE.search(text)
    if not match:
        raise SystemExit("plugin.xml has no <version>")
    return match.group(1).strip()


def build():
    staging = os.path.join(DIST, ".staging")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(HERE, staging, ignore=EXCLUDE)
    # GPL-3 §4: the licence travels with the thing that is conveyed.
    shutil.copy2(os.path.join(ROOT, "LICENSE"), staging)

    os.makedirs(DIST, exist_ok=True)
    # `<folder>_<version>.zip`: Sigil truncates at the first underscore to get
    # the folder name, so the prefix is not decoration.
    out = os.path.join(DIST, "%s_v%s.zip" % (FOLDER, version()))
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirs, files in os.walk(staging):
            for name in sorted(files):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, staging).replace(os.sep, "/")
                # Every entry must sit under that one folder, or
                # verify_plugin_zip rejects the archive.
                zf.write(full, "%s/%s" % (FOLDER, rel))
    shutil.rmtree(staging, ignore_errors=True)
    return out


if __name__ == "__main__":
    path = build()
    print("%s  (%.1f KB)" % (os.path.relpath(path, ROOT),
                             os.path.getsize(path) / 1024.0))
    sys.exit(0)
