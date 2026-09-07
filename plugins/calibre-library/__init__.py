# epubveri library check for calibre — plugin declaration
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
#
# GPL-3 is not a choice here as it is for the Sigil plugin: this one imports
# calibre's own modules at runtime, and calibre is GPL-3.

from calibre.customize import InterfaceActionBase

PLUGIN_NAME = 'epubveri library check'
PLUGIN_VERSION_TUPLE = (0, 1, 0)
PLUGIN_VERSION = '.'.join(str(part) for part in PLUGIN_VERSION_TUPLE)


class EpubveriLibraryPlugin(InterfaceActionBase):
    """Registers the library-view action.

    **This is a second zip and it has to be**, which is worth stating because
    "one plugin, two entry points" is the obvious first idea. calibre reads a
    plugin archive, collects every `Plugin` subclass it finds, and then keeps
    exactly one: `zipplugin.py`'s loader ends `ans = plugin_classes[0]`. An
    `EditBookToolPlugin` and an `InterfaceActionBase` in the same archive means
    one of them is silently discarded. The loader also keys its table by the
    import name (`loaded_plugins[plugin_name]`), so the marker file beside this
    one names `epubveri_library` rather than `epubveri`.

    The editor plugin and this one therefore ship, install and version
    separately. They share the validator binary and nothing else.
    """

    name = PLUGIN_NAME
    version = PLUGIN_VERSION_TUPLE
    author = 'Baris Kayadelen (veripublica)'
    supported_platforms = ['windows', 'osx', 'linux']
    description = (
        'Validate a whole calibre library with epubveri, a fast JVM-free EPUB '
        'validator, and report which defects recur across it. Downloads and '
        'verifies the epubveri binary on first use; nothing else is installed.'
    )
    #: Same reasoning as the editor plugin's: `qt.core` arrived with calibre 6,
    #: so 6.0 is the oldest release this can load on at all. It is not a claim
    #: about what has been tested — see the README, which names the one version
    #: it has actually run on.
    minimum_calibre_version = (6, 0, 0)

    #: The GUI half, kept in its own module so that calibre's command-line
    #: tools can load this file without pulling in Qt. `module_path:class_name`
    #: is the format calibre parses; the module is imported by name, so the
    #: import-name marker file has to agree with it.
    actual_plugin = 'calibre_plugins.epubveri_library.action:EpubveriLibraryAction'

    #: Defining `config_widget` is not what opens the settings page.
    #: Preferences / Plugins / Customize asks `is_customizable()` first and
    #: says "does not need customization" when it is false. The base
    #: implementation answers by calling `customization_help()` and catching
    #: NotImplementedError — a method belonging to calibre's *other*
    #: customization mechanism, the single `site_customization` string, which
    #: this plugin does not use. So the answer is given directly.
    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.epubveri_library.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
