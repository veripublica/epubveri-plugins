# Changelog — epubveri for calibre

Versioned independently of the Sigil plugin and of epubveri itself. The version
calibre shows comes from `PLUGIN_VERSION_TUPLE` in `__init__.py`.

## [0.2.1] — unreleased

Two things the first day of the dock showed, both reported from thread 374940.

- **The panel no longer comes back on screen at startup.** thiago.eec asked
  for it to stay hidden the way the EPUBCheck and ACE plugins do (#20) and
  Doitsu agreed (#21). Those two are dialogs and get it for free; a dock does
  not — `QMainWindow.restoreState` restores a dock's **visibility** along with
  its area and size, so a session that ended with the panel open started the
  next one with it open, over a book nothing had validated and with an empty
  panel.

  **The position is still remembered**; only the visibility is not. That is
  why this is a second, deferred close rather than dropping the `objectName`
  and giving up on `restoreState` — one request is not worth trading for
  another. calibre queues `restore_state` after `create_actions()`, which is
  where this dock is built, so the close is queued to land behind it. If a
  later calibre reorders that, the close simply happens early and the panel is
  visible again, which is today's behaviour: a wrong guess costs the request,
  not the plugin. A panel that already has findings in it is never closed
  underneath the user, whatever the timers do.

- **The rows are tinted by severity again.** thiago.eec asked for the line
  colours he had in Doitsu's plugin (#20) and Doitsu posted the set from his
  Sigil one (#21). The light palette is **his, to the byte** — pale red for
  fatal and error, which share a colour there and share one here, pale yellow
  for warning, pale cyan for info and usage — because the request is for the
  colours people already know, and two plugins that look almost alike are
  worse than two that look the same.

  **The dark theme is where this differs from his, and deliberately.** His
  paints those pale rows in both themes and forces the text black on top of
  them; that is what thiago's own 0.0.7 contribution had to do to keep them
  readable, and it makes a dark editor grow bright bands. Here the tint
  follows the theme — the same three hue families at dark lightness — and
  **no foreground is set at all**, so the text stays whatever colour the
  user's theme chose. Which theme is in use is read off the widget's own
  palette rather than asked of calibre, so it is right for a version that has
  no `is_dark_theme`, and right when someone switches theme without a
  restart.

  Advisory findings take the calm cyan: they never move the verdict. A
  severity the table does not know is left untinted rather than defaulted
  into a family, and the colour is never the only signal — the first column
  still says the word.

- **A name in the way is reported as a name in the way.** PeterT's first run
  on Linux (#19) said "epubveri could not be downloaded. The first run needs
  an internet connection" and carried `[Errno 17] File exists` in brackets.
  His connection was fine — something was already sitting where the validator
  goes (`<calibre config>/plugins/epubveri`), and the plugin blamed the
  network for a problem on the disk. He worked it out himself and called it a
  false alarm; the message was what was wrong.

  `os.path.isdir` is False both for a plain file and for a symlink whose
  target is gone, and `os.makedirs` raises the same `EEXIST` for either. Both
  now produce a sentence naming the path and saying to rename or remove it,
  and nothing is installed or changed. The folder itself is created with
  `exist_ok=True`, so two editor windows starting together cannot turn the
  same errno into a second, unrelated version of that message.

- **…and then the thing in the way turned out to be Doitsu's plugin, so we
  moved.** He was not guessed at: his 0.0.7 was read (it is in calibre's
  plugin index, `epubveri_plugin_dir()` + `epubveri_binary_name()`), and it
  keeps its copy of the binary in a **file** called
  `<calibre config>/plugins/epubveri` — exactly the name this plugin wanted
  for a folder, on Linux and macOS both. Windows was never affected; his file
  is `epubveri.exe` there.

  The collision goes both ways: his file stopped our folder being created,
  and our folder would have stopped his `copy2` — he would have ended up
  executing a directory. Neither tool can win a name, so ours moves to
  `plugins/epubveri-data`. **A folder left by 0.2.0 is moved rather than
  abandoned**, which keeps the binary this plugin already verified and hands
  the old name back to the plugin that owns it. A *file* at the old name is
  his and is never touched; a folder that does not contain our binary is
  somebody's data and is left alone too.

  This is the whole of what PeterT met, and it is not a false alarm: every
  Linux and macOS user coming from Doitsu's plugin — which is to say most of
  them — would have hit it.

- **We had also been breaking his plugin, in his own preferences file.**
  calibre keys preferences by plugin *name* and both plugins are called
  `epubveri`, so the two share one `plugins/epubveri.json`. Nine of the ten
  keys are distinct; `last_update_check` is not. His is `time.time()` and he
  computes `time.time() - last_checked`; ours was an ISO string, so his
  update check raised `TypeError` for anyone who ran this plugin and then
  his. It now writes the number he expects, and reads both spellings so no
  existing install loses its stamp. Our reader was tolerant from the start,
  which is exactly why this could only ever have shown up on his side.

## [0.2.0] — 2026-09-04

Minor rather than patch: the dock replaces the whole results interface, which
is not a fix. Still versioned independently of the Sigil plugin — the two
happening to be at 0.2.0 on the same day is a coincidence, not a pairing.

- **The plugin has an icon.** It shipped with none: the toolbar button and
  the Plugins menu entry were text and nothing else, which the owner noticed
  the moment it was installed beside the Sigil one. calibre's own idiom is
  `QAction(get_icons('myicon.png'), …)`, and `get_icons` is injected into the
  module by calibre's zip loader rather than imported — so it is looked up
  rather than called blind, because a `NameError` inside `create_action` is
  one calibre **swallows**: it prints a traceback to stderr and drops the tool
  from the menu with nothing on screen.

  It is the same mark as the Sigil plugin's, and **`icon.py` now sits at the
  repository root and writes all three copies** — `plugins/sigil/plugin.svg`,
  `plugins/sigil/plugin.png` and `plugins/calibre/plugin.png`. Each plugin
  packages itself because the editors' archive layouts differ; a brand asset
  both of them show is not that kind of difference. Tests on both sides
  compare the shipped file against what the geometry produces, and one
  compares the two plugins' copies with each other.

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
  `epubveri 0.13.3 (plugin 0.2.0) — VALID …`. Asked for by Doitsu so that a
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
