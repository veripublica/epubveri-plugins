# Changelog — epubveri for Sigil

This plugin is versioned independently of the calibre plugin and of epubveri
itself. The version Sigil shows comes from `plugin.xml`.

## [0.1.0] — unreleased

First version. An independent implementation: Doitsu's plugin proved the idea
and is what taught us what an editor integration needs, but none of its code is
here.

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
- **Updates can be turned off** by changing `"update": "yes"` to `"no"` in
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
