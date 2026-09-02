# epubveri for calibre — plugin declaration
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
#
# GPL-3 is not a choice here as it is for the Sigil plugin: this one imports
# calibre's own modules at runtime, and calibre is GPL-3.

from calibre.customize import EditBookToolPlugin

PLUGIN_NAME = 'epubveri'
PLUGIN_VERSION_TUPLE = (0, 1, 0)
PLUGIN_VERSION = '.'.join(str(part) for part in PLUGIN_VERSION_TUPLE)


class EpubVeriPlugin(EditBookToolPlugin):
    """Registers the tool with calibre's editor.

    calibre finds the `Tool` subclass through `main.py`; this class only
    declares the plugin itself. The `plugin-import-name-epubveri.txt` file
    beside it is what lets calibre import the package by name — an empty
    marker file, but the plugin will not load without it.
    """

    name = PLUGIN_NAME
    version = PLUGIN_VERSION_TUPLE
    author = 'veripublica'
    supported_platforms = ['windows', 'osx', 'linux']
    description = (
        'Validate the book you are editing with epubveri, a fast JVM-free '
        'EPUB validator. Downloads and verifies the epubveri binary on first '
        'use; nothing else is installed.'
    )
    minimum_calibre_version = (6, 0, 0)
