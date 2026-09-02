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
  cursor rather than just open the file.
- The binary is downloaded on first use and **verified against the release's
  `SHA256SUMS.txt`**. epubveri has published that file since 0.12.4 and nothing
  had been checking it.
- Usage notes and advisory checks are preferences, off by default; every run's
  summary says how many findings were hidden and where to turn them on.
- Every network call has a timeout, so a hung connection cannot freeze Sigil.
