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

from calibre.customize import EditBookToolPlugin, InterfaceActionBase

PLUGIN_NAME = 'epubveri library'
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
    #: **Listed beside its sibling rather than by its own machinery** (owner,
    #: 2026-09-07). calibre groups Preferences / Plugins by `plugin.type`,
    #: which normally comes from the base class — so this one would sit under
    #: "User interface action" and the editor plugin under "Edit book tool",
    #: two headings apart. To a user they are one product whose only
    #: difference is that one checks a book and the other a library, and both
    #: run the same epubveri; the list should say that.
    #:
    #: The cost, stated because it is real: this plugin never appears in Edit
    #: Book, so the heading describes where its *sibling* lives, not where it
    #: does. Weighed against two headings apart, the owner chose adjacency.
    #:
    #: **Nothing functional turns on `type`** — checked, all three uses in
    #: calibre 9.14 are cosmetic: the "installed under X" message
    #: (`plugin_updater.py`), the `--list-plugins` printout, and the key under
    #: which the config dialog remembers its size (`customize/__init__.py`),
    #: which resets once and never again.
    #:
    #: Taken from the class rather than typed as a literal, so it follows
    #: calibre if the wording ever changes.
    type = EditBookToolPlugin.type
    version = PLUGIN_VERSION_TUPLE
    author = 'Baris Kayadelen (veripublica)'
    supported_platforms = ['windows', 'osx', 'linux']
    #: **The description carries the cross-reference, because the category
    #: cannot.** calibre groups the plugin list by `plugin.type`, which comes
    #: from the base class and says *where in calibre a plugin works* — this
    #: one is a user-interface action, its sibling is an Edit Book tool, and
    #: they land under different headings for a true reason. Forcing them
    #: together by overriding `type` is one line and breaks nothing, but it
    #: would file a plugin that never appears in Edit Book under "Edit book
    #: tools". So each names the other instead; the list's search box does the
    #: rest, since both begin with `epubveri`.
    description = (
        'Validate a whole calibre library with epubveri, a fast JVM-free EPUB '
        'validator, and report which defects recur across it. Its companion, '
        'the "epubveri" Edit book tool, validates the one book you are '
        'editing. Downloads and verifies the epubveri binary on first use; '
        'nothing else is installed.'
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
