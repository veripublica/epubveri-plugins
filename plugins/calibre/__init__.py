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
PLUGIN_VERSION_TUPLE = (0, 3, 0)
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
    author = 'Baris Kayadelen (veripublica)'
    supported_platforms = ['windows', 'osx', 'linux']
    description = (
        'Validate the book you are editing with epubveri, a fast JVM-free '
        'EPUB validator. Downloads and verifies the epubveri binary on first '
        'use; nothing else is installed.'
    )
    #: Set by what the code imports, not by what has been tried: `qt.core`
    #: arrived with calibre 6 (before that it was `PyQt5.Qt`), so 6.0 is the
    #: oldest release this can load on at all. **It has only ever been run on
    #: 9.14**, which the README says plainly rather than letting the number
    #: here imply a range of tested versions.
    minimum_calibre_version = (6, 0, 0)

    #: calibre offers what Sigil does not: a settings page, reached from
    #: Preferences / Plugins / Customize. So this plugin asks rather than
    #: guessing. The Sigil plugin has to put the same choice in its JSON
    #: preferences file, because Sigil offers nowhere to ask.
    #: **Defining `config_widget` is not what opens the settings page.**
    #: Preferences / Plugins / Customize asks `is_customizable()` first and
    #: says "Plugin: epubveri does not need customization" when it is false
    #: (`gui2/preferences/plugins.py`). The base implementation answers by
    #: calling `customization_help()` and catching NotImplementedError — and
    #: that method is for the *other* customization mechanism, the single
    #: `site_customization` string, which this plugin does not use. So the
    #: answer is given directly rather than by raising nothing from a method
    #: that means something else.
    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.epubveri.main import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
