# Changelog — epubveri for calibre

Versioned independently of the Sigil plugin and of epubveri itself. The version
calibre shows comes from `PLUGIN_VERSION_TUPLE` in `__init__.py`.

## [0.1.0] — unreleased, incomplete

- A settings page (*Preferences / Plugins / Customize*) with one checkbox for
  automatic updates, on by default. It governs **network access** rather than
  which version runs: clearing it stops every request and says nothing more,
  while the report still says how old the binary is after a month, because
  that explains a finding rather than nagging. Written but **not run inside
  calibre** — see the status note in `README.md`.

The plugin declaration and the epubveri half are in place; the calibre user
interface is not. See the status note in `README.md` and the header of
`main.py` for exactly what is missing. **Do not package this as a release
until it has been run inside calibre.**
