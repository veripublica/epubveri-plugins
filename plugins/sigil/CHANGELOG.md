# Changelog — epubveri for Sigil

This plugin is versioned independently of the calibre plugin and of epubveri
itself. The version Sigil shows comes from `plugin.xml`.

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
