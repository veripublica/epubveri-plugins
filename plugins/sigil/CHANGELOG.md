# Changelog — epubveri for Sigil

This plugin is versioned independently of the calibre plugin and of epubveri
itself. The version Sigil shows comes from `plugin.xml`.

## [0.2.0] — unreleased

Both from Doitsu, MobileRead 374939 #21.

- **Three settings, and they are off-switches.** `show_usage`,
  `show_advisory` and `show_summary` in
  `plugins_prefs/epubveri/epubveri.json`, all defaulting to true and written
  into the file on the first run so that the file shows which choices exist.
  Someone who never opens it sees exactly what 0.1.1 showed.

  This is not a reversal of 0.1.0's "no settings" position, which was about a
  different shape: a switch you must *find and turn on* before seeing what the
  validator found would be hidden from almost everyone, Sigil having no
  settings screen. An opt-out costs nothing to the reader who never uses it.

  Three properties are enforced by tests rather than promised here:

  - **A hidden category still says so.** The summary reads `1 usage note(s)
    hidden by your settings`, so a panel with no usage notes never looks the
    same as a panel whose usage notes were filtered. This project has three
    defects on record whose only symptom was silence rather than a wrong
    answer, and a settings-driven silence is the same shape. It is also the
    only place a Sigil user can find out that these settings exist.
  - **The filter is on the display, never on the run.** `-u --advisory` are
    passed on every invocation whatever the settings say, so the counts in the
    summary describe the book rather than the preferences.
  - **Anything not clearly a no is read as yes** — the opposite of
    `autoupdate`, deliberately. There an unrecognised value must mean *off*,
    because that switch spends your connection; here it must mean *show*,
    because a reader who mistypes `flase` and is silently given less than the
    validator found has no way to notice.

  `show_summary: false` does not drop the line, it moves it: out of the
  results table and into the plugin's output window. Sigil starts this plugin
  on its own, so a table with nothing in it is what a plugin that failed to
  run produces, and "your book is clean" is worth not losing — but it does not
  have to be a *row* to be said, and a row is what anything counting results
  will count. DiapDealer's advice in MobileRead 374939 #26, and it answers
  BeckyEbook (#25) in the same move.

- **When the plugin cannot run, it now says why where the message survives.**
  Five paths report a problem and return non-zero — no binary, a failed
  integrity check, a broken envelope, a validator that would not run, a book
  epubveri could not read — and each said so with `add_result`, which on those
  paths is thrown away. Sigil's `PluginRunner::launch` checks the return value
  *first*: on anything other than zero it writes `<result>failed</result>` and
  returns before the loop that copies the plugin's results into the wrapper
  XML. So the user was told the plugin failed and nothing about why, and none
  of those five messages had ever reached anybody.

  They are printed as well now. Standard output is collected by the launcher
  and put in `<msg>` on both paths, success and failure, so it reaches the
  plugin's output window either way. DiapDealer, who maintains Sigil, gave the
  same advice for the summary line in MobileRead 374939 #26 — print it before
  returning control.

  The verdict is unaffected: a validation that *completes* returns zero
  whether the book is valid or not, which is now pinned by a test. Prompted by
  DNSB's report that an automation errored on every run after epubcheck was
  swapped for this plugin (374939 #23).

- **The archive is now `epubveri_sigil_vX.Y.Z.zip`.** Both plugins shipped a
  file called `epubveri_vX.Y.Z.zip`, so a download said nothing about which
  editor it was for and the two names would collide outright once the versions
  met (PeterT, MobileRead 374286 #275).

  Only half the name was free. Sigil takes the folder name from the archive's
  basename up to the **first** underscore and then requires every entry to sit
  under it, so `epubveri` is load-bearing and everything after it is inert —
  `sigil_epubveri_…` makes Sigil look for a folder called `sigil` and refuse
  the plugin. The two rules pull against each other, so the test asserts both:
  a rename that satisfies one and breaks the other would otherwise pass.

- **A new icon: a document with a tick knocked out of it, and no tile.**
  DiapDealer, who maintains Sigil, pointed out that Linux Sigil takes any
  theme colour imaginable and that simpler is best across three platforms
  (MobileRead 374939 #22).

  The tile it replaces was legible everywhere — it carried its own ground, so
  no theme showed through it — but that was only half the question. A filled
  tile sits in a toolbar of glyphs that are strokes on nothing and reads as a
  badge dropped into the row; and inside it the page was about 7 px wide at
  16 px with the tick at roughly 1.7 px inside that, which is the detail
  "simpler is best" is aimed at. A single-colour glyph fixes the row and
  fails the other way: it has no contrast of its own and disappears on a
  ground near its own colour.

  A filled silhouette is the third answer. It still carries its own contrast,
  so no theme shows through, but its outline is the mark rather than a
  rectangle drawn around one. Nothing in it is under 5 grid units, so the
  thinnest thing on screen at 16 px is about 1.75 px.

  It fills 44x60 of the 64 grid — as tall as a full-bleed tile, after a first
  draft that stood 35x52 and read small beside one for a real reason rather
  than an optical one.

- **`icon.py` is now the only place the icon's geometry lives**, and writes
  both `plugin.svg` and `plugin.png`. Sigil looks for the SVG and falls back
  to the PNG, so the two have to agree and nothing noticed when they did not:
  a mark edited in one and not the other is a difference only somebody on the
  other platform would ever see. Two tests compare the shipped files against
  what the geometry produces. It rasterises the PNG itself rather than
  needing rsvg-convert, Inkscape, cairosvg or Pillow — three shapes, 36
  coverage samples a pixel, `zlib` and `struct` from the standard library.

- **The summary names the plugin's version as well as epubveri's** —
  `epubveri 0.13.3 (plugin 0.2.0) — VALID …` — asked for so that a pasted line
  identifies both halves. It is read from `plugin.xml` at runtime rather than
  copied into the code, because a second copy is a second thing to forget; if
  it cannot be read the line simply omits it, a wrong version in a bug report
  being worse than an absent one.

  Worth stating plainly: most of the defects found in this plugin so far were
  in the plugin rather than in the validator, so the number that was missing
  is the one that was usually at fault.

## [0.1.1] — 2026-09-03

Both items reported the day 0.1.0 shipped, by DNSB on Windows
(MobileRead 374939 #16). Doitsu diagnosed the first one.

- **A result about the book as a whole no longer says "*** Invalid Book Path
  Provided ***".** The summary line named no file by passing an empty string,
  and an empty bookpath is how Sigil's result table is told to complain rather
  than how it is told there is none: `ValidationResultsView::DisplayResults`
  prints that text for an empty path and the path itself for anything else. It
  now passes a single space, which is neither empty nor a path, so the File
  column comes out blank. Doitsu's suggestion was `None`, which also clears the
  message; it reaches the table as the literal word "None", so a space is used
  instead. Reported against the summary line, and the same empty string was in
  seven other places — every failure before the book is read, and **every
  finding epubveri reports about the container rather than about a file**. All
  of them are fixed, and no result may carry an empty bookpath now: a test
  asserts it over the whole run.
- **Positions in content.opf now land in the document Sigil is showing.**
  The panel said line 95 and the cursor went to 96, in the OPF only. 0.1.0
  overwrote the copied OPF with `get_opf()`, and that is a *rebuild* from
  Sigil's model — it sorts the manifest by `id` and rewrites every entry as
  `<item id= href= media-type= />`. Our line numbers and character offsets
  were correct for that rebuild and for nothing else: on the book that found
  it, the cover entry is at line 91 in the file, 95 in the rebuild, and 96 in
  what Sigil displayed. The substitution was there so unsaved manifest and
  spine edits would be validated, and it was never needed — the OPF is not a
  manifest item, so `copy_book_contents_to` fetches it through
  `Wrapper.readotherfile`, which already returns the live rebuild when the
  book has unsaved OPF edits and the file from the ebook root otherwise. So
  removing it keeps the unsaved edits and gets the positions back. Nothing is
  substituted after the copy now, and a test asserts it.
- **The plugin has an icon**, so Manage Plugins and the toolbar show something
  other than a placeholder. Shipped as `plugin.svg` with a `plugin.png`
  beside it, which is the order Sigil looks in. It is a filled tile rather
  than a line drawing because Sigil has a dark theme too, and a single-colour
  outline vanishes into one of the two.

Also confirmed by this thread, and worth recording because 0.1.0 said the
opposite was unknown: it runs on **Windows** (DNSB) and on **Linux**, the
AppImage build on an Intel Chromebook (PeterT). At release, two people had run
it on macOS and nobody had tried it anywhere else.

## [0.1.0] — 2026-09-03

First version. An independent implementation: Doitsu's plugin proved the idea
and is what taught us what an editor integration needs, but none of its code is
here.

- `autostart` is on, so choosing the plugin runs it. Doitsu suggested it and
  Sigil's source says why it matters: with it off the runner shows a dialog
  whose only content is a Start button, and a validation asks nothing, so that
  is a click for nothing. `autoclose` is deliberately left alone — `PluginRunner`
  already accepts and closes for any plugin of type `validation`.
- Validates the open book, including unsaved edits: the OPF Sigil currently
  holds is written into the temporary container rather than the one on disk.
- Findings carry file, line and **character offset**, so Sigil can place the
  cursor rather than just open the file. Sigil uses the offset in preference
  to the line number, so it has to be an absolute document position; the first
  build indexed a 0-based table with a 1-based line number and highlighted one
  line late.
- The binary is downloaded on first use and **verified against the release's
  `SHA256SUMS.txt`**. epubveri has published that file since 0.12.4 and nothing
  had been checking it.
- **Every finding is listed and there are no settings.** Sigil offers a plugin
  no configuration screen, so a preference would have been a switch the user
  could not reach. Each line is labelled instead — `ERROR`, `WARNING`, `USAGE`,
  `ADVISORY` — and every advisory carries "epubcheck does not report this; the
  verdict is unaffected". Only errors, fatals and warnings decide VALID/NOT
  VALID, exactly as in epubcheck.
- Every network call has a timeout, so a hung connection cannot freeze Sigil.
- **Keeps epubveri current on its own**, by comparing checksums rather than
  version numbers: at most once an hour it reads the release's
  `SHA256SUMS.txt` (842 bytes, no GitHub API, no `epubveri -V`) and compares
  one line against the hash it stored. Smaller than asking the API — 31 KB of
  JSON, rate-limited — and stricter, since it also catches an archive
  re-uploaded under the same tag or a local copy that has been replaced.
  Without any of this a user would be pinned to whatever shipped the day they
  installed the plugin, and almost every recent epubveri release fixed a wrong
  error on a valid book. A failed check is silent and is recorded, so an
  offline machine makes one failed request an hour rather than one per book.
- **The binary is verified before every run**, not only when it is downloaded.
  Its checksum is recorded at install and compared each time; if the file has
  changed the plugin reports it and runs nothing. Verifying at download proves
  what arrived, and between arriving and running sits everything that can
  touch a file. 1.8 ms for 2.8 MB, under one percent of a validation. A
  missing stored hash means an upgrade from a version that recorded none, and
  is trusted once rather than refused.
- **Updates can be turned off** by changing `"autoupdate": true` to `false` in
  `plugins_prefs/epubveri/epubveri.json`. The key is **written there on the
  first run** rather than only read, so the file shows that the choice exists —
  Sigil has no settings screen, so a key that were merely honoured would be
  invisible. Anything not clearly a yes is read as no, since using someone's
  connection after they declined is the worst thing this switch can do. The
  preference governs the *network*, not the version, so the age line below
  still appears.
- **Offline is silent** — measured over 144 validations across three days with
  no network: no error, no warning, nothing missing. After **thirty days**
  without a successful check the summary adds one line saying how old the copy
  is, because by then it may be reporting something already fixed. That needs
  a separate `last_update_success`: the ordinary stamp is written even when a
  check fails, so it can never say how old the binary is.
- **Findings are escaped for Sigil's result XML.** Sigil builds that document
  by raw interpolation and escapes only some of its own strings, so a message
  containing a double quote ended the attribute and Sigil answered "Error
  Parsing Result XML" — showing *nothing at all*, on a book with 257 findings.
  epubveri quotes element and attribute names the way epubcheck does, so this
  affected 39 of those 257.
- The archive is `epubveri_vX.Y.Z.zip`, and the name is not decoration: Sigil
  derives the plugin folder from the filename up to the first underscore and
  rejects the archive if the folder inside does not match. A test now checks
  the whole contract against Sigil's own rule.
