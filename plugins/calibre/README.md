# epubveri for calibre

Validates the book open in calibre's **Edit Book** tool with
[epubveri](https://github.com/veripublica/epubveri) — no Java, sub-second, and
reporting epubcheck's own message IDs so the output is recognisable.

> **Status: not released.** The half that talks to epubveri is finished and is
> the same code the Sigil plugin's tests exercise. The half that talks to
> calibre is written against its published plugin API and has **not been run
> inside calibre**, so there is no download for it yet. What is missing is
> listed at the top of `main.py`: a results view, jumping the editor to a
> finding, the preferences page, and the update check.

## Why it is a separate plugin rather than a mode of the Sigil one

They are applications for different programs. This one lives inside calibre's
editor and uses calibre's own facilities — `JSONConfig` for preferences,
`iswindows` for platform tests, calibre's plugin-directory conventions — where
the Sigil plugin has Sigil's `bk` container. The two share a language and
nothing else, so each carries its own copy of the code that talks to epubveri
and neither can break the other.

## Installing (once there is a release)

1. Download `calibre_epubveri_vX.Y.Z.zip` from
   [Releases](https://github.com/veripublica/epubveri-plugins/releases).
2. **Preferences → Plugins → Load plugin from file**, choose the zip.
3. Restart calibre. The tool appears in the Edit Book toolbar and Plugins menu.

On first use it downloads the epubveri binary for your platform and verifies it
against the release's `SHA256SUMS.txt`. The plugin zip contains no binary.

## Licensing

GPL-3.0-only, and here that is a requirement rather than a choice: this plugin
imports calibre's own modules at runtime and calibre is GPL-3. (The Sigil
plugin is under the same licence by choice — Sigil's plugin interface is BSD.)

## Reporting a problem

Issues here: <https://github.com/veripublica/epubveri-plugins/issues>. A wrong
finding rather than a wrong plugin belongs in
[epubveri](https://github.com/veripublica/epubveri/issues).
