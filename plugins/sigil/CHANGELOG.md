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
- Usage notes and advisory checks are preferences, **off by default but
  announced**: epubveri is run with both on and the filtering happens at
  display, so the summary can name what it hid — "1 usage note(s), 1 advisory
  finding(s) epubcheck does not make" — instead of leaving a checkbox to be
  discovered. Switching either on does not re-validate the book. Off is the
  right default (an unasked-for finding reads as a wrong one to anyone
  comparing the two tools), but a switch nobody knows about is a feature
  nobody has.
- Every network call has a timeout, so a hung connection cannot freeze Sigil.
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
