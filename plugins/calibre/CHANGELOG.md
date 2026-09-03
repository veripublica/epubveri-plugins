# Changelog — epubveri for calibre

Versioned independently of the Sigil plugin and of epubveri itself. The version
calibre shows comes from `PLUGIN_VERSION_TUPLE` in `__init__.py`.

## [0.1.0] — unreleased

Written and, for the first time, **exercised inside calibre**: the plugin
installs, registers as an Edit Book tool and imports. The GUI itself has still
not been driven by hand — no menu has been clicked — so this is not a release.

- **The tool.** One entry in the editor's Plugins menu and toolbar. It writes
  the book as the user currently has it, runs epubveri, and lists every
  finding with its file, line and message.
- **Findings navigate.** Activating a row opens the file and puts the cursor
  on the line, the same way `Boss.check_item_activated` does for calibre's own
  Check Book results. Both conventions were read off `TextEdit.go_to_line`
  rather than assumed: the **line is 1-based and the column is 0-based**, and
  calibre clamps a column past the end of a line — so the overshoot that moved
  Sigil's cursor one line down cannot happen here.
  - calibre's own Check Book panel is **not** used: `run_checks` calls
    calibre's checkers directly and accepts no plugin, so there is no hook.
    Reaching into that panel would mean depending on its internals.
- **The book is packaged without touching the user's copy, and this is
  measured rather than argued.** Unsaved edits are committed to the container
  first (`boss.commit_all_editors_to_container()`, which calibre's own
  docstring tells you to call), and then the container is **cloned** and the
  clone written out. `EpubContainer.commit` calls `update_modified_timestamp`
  on an EPUB 3 book, so committing the real container would rewrite
  `dcterms:modified` — a validation would edit the book. Probed on one EPUB 2
  and one EPUB 3 book: the file on disk is byte-identical afterwards, the
  clone's timestamp did move (2021 → 2026, which is the proof the hazard is
  real), and epubveri reports **exactly the same findings** from the clone as
  from the original — 14 and 42, same codes, files and line numbers.
  - `clone_container` links rather than copies, which is safe:
    `get_file_path_for_processing` decouples a file from its links before
    writing to a cloned container.
  - **`clone_dir` requires its destination to exist**, which its docstring
    says and the first run proved: without `os.makedirs` it fails on
    `META-INF`. Found by running it, not by reading it.
- **`is_customizable()` has to say so.** Providing `config_widget` and
  `save_settings` is not what opens the settings page: Preferences → Plugins →
  Customize asks `is_customizable()` first and otherwise answers "Plugin:
  epubveri does not need customization" (`gui2/preferences/plugins.py`). The
  base implementation decides by calling `customization_help()` and catching
  `NotImplementedError`, and that method belongs to calibre's *other*
  customization mechanism — the single `site_customization` string — which
  this plugin does not use. Found by the owner on the first click.
- **A settings page** (*Preferences → Plugins → Customize*) with three
  checkboxes: automatic updates, show usage notes, show advisory findings.
  All three default to on, so out of the box calibre and Sigil report the same
  book identically. Whenever a switch hides something, the summary says how
  many findings are not listed and where the setting is — never a silently
  shorter report.
  - The update box governs **network access** rather than which version runs:
    clearing it stops every request and says nothing more, while the report
    still says how old the binary is after a month, because that explains a
    finding rather than nagging.
- **The binary is verified before every run** and kept current at most once an
  hour, the same policy as the Sigil plugin, against the release's
  `SHA256SUMS.txt`.
- The plugin imports its own package (`calibre_plugins.epubveri.client`)
  instead of pushing its folder onto `sys.path` and importing `client`. That
  name is one any other plugin might also use, and the first one imported
  would have won for both.

**Still to do before this is released:** drive it by hand in calibre's editor,
on all three platforms, and a test suite of its own.
