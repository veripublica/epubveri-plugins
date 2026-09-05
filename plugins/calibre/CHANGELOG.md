# Changelog — epubveri for calibre

Versioned independently of the Sigil plugin and of epubveri itself. The version
calibre shows comes from `PLUGIN_VERSION_TUPLE` in `__init__.py`.

## [0.4.0] — unreleased

The last two things Doitsu asked for in post 21, and everything thiago.eec
and he said the next day about 0.3.0 (posts 22 and 23).

- **The CSV exports everything again.** thiago.eec: "The CVS exports only the
  selected line. Is this intentional? JSON exports the full report." (#22) It
  was not intentional in the sense he means — 0.3.0 asked the table whether
  anything happened to be selected instead of being told what was wanted. The
  menu now has *Save all rows as CSV…* and, when there is a selection, *Save
  selected rows as CSV…*; only the one that says "selected" means it. Doitsu
  asked for the same thing (#23).

- **An export is offered under the book's own name.** Every one used to be
  proposed as `epubveri-results.csv`, so exporting a selection after the whole
  table landed on the first file, and a folder of them said nothing about which
  book was which. Now:

  ```
  Suç ve Ceza (Dostoyevski)-epubveri-all-57.csv
  Suç ve Ceza (Dostoyevski)-epubveri-selected-3.csv
  Suç ve Ceza (Dostoyevski)-epubveri-report-63.json
  ```

  Which book, which part of it, how much. The stem is the file calibre is
  editing — the same one its title bar shows — and calibre's own sanitiser
  keeps a title with a slash or a colon from proposing a path. The scope stays
  a word beside the count, because a number does not say what it counts, and a
  selection of every row would otherwise be offered under the name of the whole
  table. The count is the owner's idea and earns its place the moment a book
  changes between two exports.

  The same book, same scope, unchanged, twice still offers the same name — and
  the save dialog asks before replacing, which is the right place for that
  question.

- **Every CSV field is quoted.** Doitsu again, who called it "more 'robust'".
  `csv` quotes for the comma on its own; the case that needs this is the
  **semicolon**, because a spreadsheet whose list separator is `;` — a German
  or Turkish locale — splits an unquoted message containing one straight down
  the middle. A quoted field survives either separator.

- **There is a Col column.** Doitsu: "Since the Calibre API allows to position
  the cursor by line _and column_, it'd be helpful, if you added a Column
  column." (#23) It was left out of 0.3.0 on purpose — the number is used
  rather than read, since a double-click puts the cursor on that character —
  and the note recording that decision said the answer if anyone asked would
  be that this is a small change and not a principle. Somebody asked. It sorts
  as a number, like Line.

- **The panel's background and the severity colours are two settings now,**
  under *Appearance* in the same page. thiago.eec, of the dark-theme set: "I'd
  rather have the same colors in a dark theme. The new bacground colors are
  better than no color at all, but not as good as the original colors." (#22)

  That is a preference, not a defect, and the owner's call was that it should
  not be settled by argument at all: `panel_theme` is `auto` (follow calibre),
  `light` or `dark`, and `row_colors` is `theme` (follow the panel) or `pale`
  (the light set in both, as Doitsu's plugins and Sigil use, with the text
  forced dark so it stays readable). **Both default to what 0.3.0 shipped**,
  so anyone who does not care sees no change; the combinations people asked
  for — a dark panel with pale rows, or a light panel inside a dark calibre —
  are two clicks.

- **A clean book no longer opens the panel.** His words: "if no problems were
  found, simply display a message box instead of an empty widget." A panel
  that opens to say nothing takes screen space at the moment you are finished
  with it, so the verdict goes in a box and the dock stays shut.

  Minor rather than patch because of that: it is a change in what the plugin
  does, not a fix. **A panel that was already open is still refilled** — the
  previous book's findings sitting under a clean verdict would be worse than
  either — but it is neither opened nor raised. A book whose every finding is
  hidden by your display settings counts as nothing to list, and the box then
  carries the line saying how many were hidden and where the switch is.

- **The status bar says what is happening.** He asked for a word while the
  book is being checked, while an update is being looked for or fetched, and
  how that turned out — so there are messages for all four, plus the verdict
  when the run ends. calibre's own `show_status_message` is used where it
  exists and the bar directly where it does not, since
  `minimum_calibre_version` claims releases this was not checked in.

  The messages are painted with `processEvents`, which is not decoration: a
  validation runs on the UI thread, so a line set before the work would
  otherwise appear only once the thing it describes had finished.

## [0.3.0] — 2026-09-04

Minor rather than patch: two of these change what the panel does, not only
what it gets right. Everything here was reported in thread 374940 on the
first day the dock existed.

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

- **The settings are reachable from inside the editor.** thiago.eec asked
  for that (#20) and Doitsu suggested where (#21): the toolbar button now has
  a dropdown. Clicking the button still validates — `toolbar_button_popup_mode
  = 'button'` is calibre's `MenuButtonPopup`, so the click keeps the meaning
  it had — and the arrow opens *Validate now*, *Show the results panel* and
  *epubveri settings…*. The results panel's right-click menu has the settings
  entry too, which is the other moment you want them: you are looking at the
  rows a setting decides.

  It is **the same page** calibre builds under Preferences → Plugins →
  Customize, in a dialog of our own — one page, two doors, so the two can
  never drift into offering different things.

  **Changing a setting re-lists the run already in hand**, without validating
  again: the switches decide what is *listed* and the whole report is already
  here. Someone who turns usage notes on and sees nothing change would
  reasonably conclude the setting does not work. The sort setting applies
  immediately too, this once — it is otherwise applied only when a session's
  first results arrive, so that a header click is not undone by validating
  again, but a person who has just chosen an order in the dialog means now.

  *Show the results panel* exists because the dock is hidden at startup and
  closable: without it, a user who has closed the panel has no way back to the
  last run's findings except by validating a book that has not changed.

- **Fixed before it shipped: the column you sorted by was not the one that
  came back.** The loop that tints each row reused the name holding the sort
  column, so after a re-validation the table sorted by whichever column
  happened to be last — Message. It looked plausible, because it *was*
  sorted; it simply was not sorted by what the user had clicked. Found while
  proving another test could fail, which is the argument for that habit: the
  bug was in the same commit as the feature and no green suite would have
  shown it.

- **Rows can be selected, copied and exported.** Doitsu asked for the three
  together (#21) and they are one feature: a panel you cannot get text out of
  makes people retype findings or photograph them. Ctrl+click and Shift+click
  select; **Ctrl+C** copies the selection as tab-separated lines, in the order
  on screen, because the two things people do with this are paste it into a
  forum post and paste it into a spreadsheet. Right-click for the rest: copy
  everything, select all, and the two exports.

  The clipboard write is retried with a read-back, which is not defensive
  coding for its own sake — Doitsu's plugin documents the reason and it is a
  fact about Windows rather than about Qt: `SetClipboardData` fails outright
  while another process has the clipboard open, nothing retries, and the copy
  silently does nothing.

  **The two exports answer different questions, on purpose.** *Save the table
  as CSV* writes what you are looking at — your display settings, your sort
  order — through Python's `csv` writer, because epubveri's messages carry a
  comma and a double quote in the same sentence and a handmade writer gets one
  of them wrong. *Save epubveri's full report as JSON* writes the envelope
  whole, filtered by nothing, in the format the other veripublica tools read.
  That is the file to attach when something looks wrong, and someone who has
  switched usage notes off must not send a report with the usage notes
  missing.

  Ctrl+C and Ctrl+A are bound to the table rather than to the window: the
  editor has its own Ctrl+C, and a shortcut that reaches past the widget it
  belongs to takes it away from the text being edited.

- **Sortable columns, opening severest first.** thiago.eec asked for
  sortable columns "particularly by severity" (#20); Doitsu agreed (#21).
  Click any header to reorder, click again to reverse — and the first column
  is called **Severity** now, because a column you are meant to click has to
  say what it is.

  Two things a table like this gets wrong when it is simply handed to Qt, and
  both are avoided here: **severity would sort alphabetically**, which orders
  it ERROR, FATAL, INFO, USAGE, WARNING and puts a fatal below an error; and
  **the line number would sort as text**, putting line 10 before line 9.
  Sigil's own results table has the second one. Ranking is by severity with
  advisories last — they never move the verdict — and every column breaks ties
  on the order epubveri produced the findings in, so **each severity group
  still reads top-to-bottom**, which is what epubveri's own `--sort severity`
  promises.

  **The panel now opens severest first**, where before it opened in the order
  the validator emitted. Three things already agreed on that order and this
  plugin was the one out of step: epubveri's CLI shows a person severity-first
  by default, calibre's own Check Book sorts `(100 - level, name)`, and — the
  one nobody had noticed — **the Sigil plugin has always sorted by severity**.
  The JSON envelope is in document order on purpose, so that a tool never
  inherits an order its user chose; picking one is the plugin's job and it had
  not been done.

- **A setting for that order:** *Preferences → Plugins → epubveri → Customize*.
  Three values, and they are epubveri's own `--sort` words rather than a
  vocabulary invented for plugins: `severity` (the default), `severity-low`,
  `document`. It decides how the panel **opens**; a header click beats it for
  the rest of the session and nothing about the order survives a restart. An
  order chosen for one book is a passing thought, not a setting.

  `document` is offered by **not sorting at all** — Qt has no unsorted state
  once sorting is enabled — and clicking a header still works from there, so
  choosing it does not cost the feature.

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
