# epubveri for calibre

Checks the book open in calibre's **Edit Book** tool against the EPUB
specification with [epubveri](https://github.com/veripublica/epubveri) — no
Java, sub-second, and reporting epubcheck's own message IDs so the output is
recognisable. **It reads your book and reports; it changes nothing.**

> **Released as [0.1.0](https://github.com/veripublica/epubveri-plugins/releases/tag/calibre-v0.1.0),
> and it has run on calibre 9.14 on macOS and nowhere else.** Nothing has been
> tried on Windows or Linux, and no other calibre release has loaded it. The
> declared `minimum_calibre_version` is 6.0 because that is when `qt.core` —
> which this plugin imports — replaced `PyQt5.Qt`: it is the oldest release the
> plugin *can* load on, not the oldest it has been run on.
>
> Doitsu's calibre plugin has been in users' hands far longer; if this one
> misbehaves, that is the one to fall back to.

## Why it is a separate plugin rather than a mode of the Sigil one

They are applications for different programs. This one lives inside calibre's
editor and uses calibre's own facilities — `JSONConfig` for preferences,
`iswindows` for platform tests, calibre's plugin-directory conventions — where
the Sigil plugin has Sigil's `bk` container. The two share a language and
nothing else, so each carries its own copy of the code that talks to epubveri
and neither can break the other.

## Installing

1. Download `epubveri_calibre_vX.Y.Z.zip` from
   [Releases](https://github.com/veripublica/epubveri-plugins/releases) —
   the one tagged **`calibre-`**, since this repository releases both plugins
   and GitHub's "Latest" badge only means newest by date.
2. **Preferences → Plugins → Load plugin from file**, choose the zip.
3. Restart calibre. The tool appears in the Edit Book toolbar and Plugins menu.

On first use it downloads the epubveri binary for your platform (~3 MB) and
verifies it against the release's `SHA256SUMS.txt` before it is ever run. The
plugin zip contains no binary. It is kept in
`<calibre config>/plugins/epubveri/` rather than beside the plugin, because
**calibre imports a plugin straight out of its zip and never unpacks it** —
there is no plugin folder to put anything in.

## Reading the results

Every finding gets a row with its file, line and message, labelled `ERROR`,
`WARNING`, `USAGE` or `ADVISORY`. **Activating a row opens the file and puts
the cursor on the line**, the same way calibre's own Check Book results do.

Only errors, fatals and warnings decide VALID or NOT VALID, exactly as in
epubcheck. Advisories are epubveri's own checks; each one says so on its line,
and none of them can change the verdict.

Unsaved edits are included: what calibre currently holds is what gets
validated, not the file on disk.

## Settings

*Preferences → Plugins → epubveri → Customize*, three switches, **all on by
default** so that out of the box calibre and Sigil report the same book
identically.

**Keep epubveri up to date automatically.** This one is about *the network*
rather than the version: clearing it stops every request — for a metered
connection, an air-gapped machine, or preference — and nothing is said about it
afterwards. What it does not stop is the line telling you how old your copy is
after a month without a check: that is an explanation for a finding that looks
wrong, not a nag.

**Show usage notes.** Findings epubcheck also reports but hides unless you pass
`-u`. Not errors, and they never change the verdict.

**Show advisory findings epubcheck does not make.** epubveri's own `ADV-*`
checks.

Turning either display switch off makes the panel shorter, never quieter about
it: the summary then says how many findings are not listed and where the
setting is. Neither switch can hide an error or a warning.

Sigil has no settings screen for a plugin at all, so its half of this
repository writes the update setting into its JSON preferences file for the
user to edit by hand — same key, `autoupdate`, same meaning — and shows
everything else.

## Licensing

GPL-3.0-only, and here that is a requirement rather than a choice: this plugin
imports calibre's own modules at runtime and calibre is GPL-3. (The Sigil
plugin is under the same licence by choice — Sigil's plugin interface is BSD.)

## Reporting a problem

Issues here: <https://github.com/veripublica/epubveri-plugins/issues>. A wrong
finding rather than a wrong plugin belongs in
[epubveri](https://github.com/veripublica/epubveri/issues).
