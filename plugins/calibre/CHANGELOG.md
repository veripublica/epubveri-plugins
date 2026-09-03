# Changelog — epubveri for calibre

Versioned independently of the Sigil plugin and of epubveri itself. The version
calibre shows comes from `PLUGIN_VERSION_TUPLE` in `__init__.py`.

## [0.1.1] — unreleased

- **The results are a dock now, not a window.** Doitsu asked for one "like
  Calibre's check book tool" (MobileRead 374940 #16) and JSWolf said that was
  more than a nitpick (#17). They were right: the dialog had the correct
  behaviour and the wrong shape. Docking, tabbing behind another panel, and a
  position that is still there next week are what a panel gets for free and a
  floating window never does.

  This is **not** calibre's own Check Book panel, which stays closed to
  plugins — `run_checks` calls calibre's checkers directly and takes no
  plugin. A dock of our own is as close as a plugin can get.

  Two details make it behave like calibre's own. It is created from
  `create_action`, which `Main.__init__` runs *before* `create_docks()` and
  well before it defers `restore_state`, so the dock exists by the time
  `restoreState` runs and **calibre remembers its area, size and visibility
  for us** — there is nothing of ours stored anywhere. And it carries an
  `objectName`, which is what that restore is keyed on; calibre's own docks
  set one with the comment "Needed for saveState".

  It starts hidden and a validation brings it up, the way Live CSS does.
  Validating again clears and refills the one panel: the dialog had to close
  its predecessor by hand or three validations left three windows, two of them
  describing a book that had since been edited.

- **The summary names the plugin's version as well as epubveri's** —
  `epubveri 0.13.3 (plugin 0.1.1) — VALID …`. Asked for by Doitsu so that a
  pasted line identifies both halves (MobileRead 374939 #21). It comes from
  the same `PLUGIN_VERSION_TUPLE` calibre reads for Preferences, so there is
  no second copy to bump. Most of what has gone wrong in these plugins so far
  was the plugin rather than the validator, which makes it the more useful of
  the two numbers to have been missing.

- **The archive is now `epubveri_calibre_vX.Y.Z.zip`.** Both plugins shipped
  a file called `epubveri_vX.Y.Z.zip`, so a download said nothing about which
  editor it was for and the two names collided outright once the versions met
  (PeterT, MobileRead 374286 #275). calibre reads the plugin name from the
  class and the import-name marker, so its archive name means nothing to it
  and was free to change; the Sigil one had to keep `epubveri` before the
  first underscore.

- **The test harness now runs the real `__init__.py`.** Its stand-in for
  `calibre_plugins.epubveri` was an empty module with a search path, so the
  package the tests saw had none of the constants the package really defines
  — a module-level import of `PLUGIN_VERSION` worked inside calibre and
  failed here. A harness that differs from production in what it *defines*
  keeps producing that shape of failure.

## [0.1.0] — 2026-09-03

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
- **Nothing in the packaged book is re-serialised, and cloning alone did not
  achieve that.** `EpubContainer.commit` calls `update_modified_timestamp()`,
  which dirties the OPF, and a dirtied file is rewritten rather than copied.
  calibre's serialiser is not byte-preserving: on the test fixture it split
  `<dc:title>T</dc:title><dc:language>en</dc:language>` onto two lines and
  wrote `<dc:creator/>` for `<dc:creator></dc:creator>`, so the OPF gained a
  line and **every finding below it was reported one line off** — the Sigil
  defect arriving by a different route. The clone's timestamp update is
  neutralised, so the OPF stays undirtied and is copied verbatim. Every file
  in the produced `.epub` is now byte-identical to the container's, edited
  files included (`commit_editor_to_container` writes the editor's bytes with
  no parse).
  - **Found by the test suite, not by a person** — the first defect in this
    repository that was. Two real books had missed it: an EPUB 2 one never
    triggers the timestamp update at all, and an EPUB 3 one happened to
    re-serialise to the same number of lines.
- **A test suite of its own**, 13 tests, run inside calibre's interpreter with
  `calibre-debug plugins/calibre/tests/test_plugin.py`. It uses the same book
  fixture as the Sigil plugin's tests, so a disagreement between the two
  plugins is about a plugin and never about the fixture. Both packaging tests
  were checked by removing the fix and watching them fail.
  - `unittest.main()` finds nothing under `calibre-debug`, which runs a script
    in a fresh globals dict rather than as `sys.modules['__main__']`. It
    reports "NO TESTS RAN" rather than failing, which is the kind of green
    that means nothing, so the suite is built from the module's own namespace
    and refuses to run if it collects none.
- **A second validation replaces the first window** instead of opening another
  beside it. The dialog is non-modal on purpose — activating a row moves the
  editor behind it — so nothing otherwise stopped them accumulating, each older
  one reporting a book that has since been edited.
- `minimum_calibre_version` is 6.0 because that is when `qt.core` replaced
  `PyQt5.Qt`; it is the oldest release the plugin can load on, not the oldest
  it has been run on. **It has only ever run on 9.14, on macOS**, and the
  README says so.
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

**Still open:** no platform but macOS has run it, and no calibre but 9.14.
That is what a first release is for — Sigil's Windows and Linux reports both
arrived the day after its own.
