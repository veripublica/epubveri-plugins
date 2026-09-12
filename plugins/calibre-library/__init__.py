# epubveri library for calibre — plugin declaration
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

PLUGIN_NAME = 'epubveri library'
PLUGIN_VERSION_TUPLE = (0, 4, 0)
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

    #: **This string is calibre's identity key for the action**, not just a
    #: label: `gprefs['action-layout-*']` stores it, so renaming it orphans
    #: every placement a user already has and calibre offers the placement
    #: dialog again. The orphaned entries are inert — `bars.py` skips a name
    #: it does not know — but they stay in the config until removed by hand.
    #: Worth knowing before the next rename.
    #:
    #: Not "epubveri library check": `check` is the word in `epubcheck`, which
    #: is W3C's mark and one this project does not imitate.
    name = PLUGIN_NAME
    #: **Its own category, after calibre's own community named it one**
    #: (owner, 2026-09-10). This used to be forced to `EditBookToolPlugin.type`
    #: so the two plugins would sit under one heading in Preferences /
    #: Plugins: to a user they are one product whose only difference is that
    #: one checks a book and the other a library, and two headings apart said
    #: otherwise.
    #:
    #: The cost was stated when that choice was made — this plugin never
    #: appears in Edit Book, so the heading described where its *sibling*
    #: lives — and it has now been paid. On MobileRead a moderator retitled
    #: the thread to **[GUI Plugin] epubveri library** and Comfy.n placed it
    #: under *Extend calibre generally* (375207 #3, #6, #7). That is the
    #: calibre community answering the same question, and answering it the
    #: other way: this is a GUI plugin. A Preferences list that files it under
    #: "Edit book tool" now disagrees with the forum index a user found it in.
    #:
    #: So it takes the type its own base class gives it, and the two plugins
    #: name each other in their descriptions instead — which they already did,
    #: because the category never could.
    #:
    #: **Nothing functional turns on `type`** — checked, all three uses in
    #: calibre 9.14 are cosmetic: the "installed under X" message
    #: (`plugin_updater.py`), the `--list-plugins` printout, and the key under
    #: which the config dialog remembers its size (`customize/__init__.py`),
    #: which resets once and never again. That was the reason it was safe to
    #: override, and it is the reason it is safe to stop.
    version = PLUGIN_VERSION_TUPLE
    author = 'Baris Kayadelen (veripublica)'
    supported_platforms = ['windows', 'osx', 'linux']
    #: **One line, because the plugin list is a list** (owner, 2026-09-12).
    #: This ran to three lines where calibre's own entries run to one — "Copy
    #: a book from one calibre library to another" — so in a column of short
    #: rows ours was the tall one, which reads as a plugin that needs
    #: explaining.
    #:
    #: What it gives up is the cross-reference to the sibling plugin. That was
    #: put here because `plugin.type` files the two under different headings
    #: and cannot say they belong together — a real argument, which lost to a
    #: worse cost: the reference sat three lines into a paragraph nobody
    #: finishes. It is in the README, in the forum thread, and on the settings
    #: page beside the validator, where somebody is already reading.
    #:
    #: The name is not repeated either. The row above this text already says
    #: "epubveri library", and calibre's own descriptions never restate their
    #: plugin's name.
    description = (
        'Validate every EPUB in your library and report the defects that recur'
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
