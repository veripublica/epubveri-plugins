# epubveri for Sigil

Checks the book you have open in [Sigil](https://sigil-ebook.com/) against the
EPUB specification with [epubveri](https://github.com/veripublica/epubveri),
and puts each finding on the line it belongs to. **It reads your book and
reports; it changes nothing.**

Sigil already has a validation panel; this adds a second opinion to it — one
that needs no Java, answers in well under a second, and reports epubcheck's own
message IDs (`RSC-005`, `OPF-030`, …) so the output is recognisable to anyone
who has used epubcheck.

## Installing

1. Download `epubveri_vX.Y.Z.zip` from
   [Releases](https://github.com/veripublica/epubveri-plugins/releases).
   **Do not rename it.** Sigil takes the folder name from the part of the
   filename before the first underscore, and refuses the plugin if it does not
   match what is inside.
2. In Sigil: **Plugins → Manage Plugins → Add Plugin**, choose the zip.
3. Run it from **Plugins → Validation → epubveri**.

**On first use it downloads the epubveri binary** for your platform from
epubveri's own releases, checks it against that release's `SHA256SUMS.txt`, and
keeps it beside the plugin. Nothing else is installed, and the plugin zip
contains no binary. Roughly 3 MB, once.

## What you will see

Findings land in Sigil's validation panel with their file, line and column, so
double-clicking one takes you to the character rather than the file.

The verdict is epubcheck's: **a book that passes epubcheck passes epubveri.**
The last line of every run says which version validated the book, the verdict,
and how many findings were hidden.

## What is in the report, and what decides the verdict

**Everything epubveri found is listed — there are no settings to find.** Sigil
gives a plugin no configuration screen, so a preference would have been a
switch you could not reach.

Every line says what it is, and only two kinds decide the verdict:

| label | what it is | counts towards the verdict |
|---|---|---|
| `FATAL` / `ERROR` | the book breaks the specification | **yes** |
| `WARNING` | epubcheck warns about it | **yes** |
| `INFO` | epubcheck says it for information | no |
| `USAGE` | worth knowing, not a defect — an unreferenced image, a `@font-face`. epubcheck reports these too, but only with `-u` | no |
| `ADVISORY` | **epubcheck does not report this at all.** `NEXT-*` is something a published specification requires and epubcheck has not implemented yet; `ADV-*` is where no specification says anything but the book is still probably wrong | no |

Every advisory line carries the sentence *"epubcheck does not report this; the
verdict is unaffected"*, so it cannot be mistaken for the two tools
disagreeing. On the command line these are opt-in (`-u`, `--advisory`), because
a script diffing epubveri against epubcheck has to see the same report from
both. A results panel is not a diff — it has a Type column — so here you get
everything and judge for yourself.

**A book that passes epubcheck passes epubveri**, with or without any of this.

## If something goes wrong

- **"epubveri could not be installed"** — the download or its checksum failed.
  The message says which. A checksum failure means nothing was installed.
- **No epubveri build for this platform** — the release covers Linux, macOS and
  Windows on x86-64 and ARM64. Anything else has to be built from source.
- The plugin never modifies your book. It writes a temporary copy, validates
  that, and deletes it.

## Reporting a problem

Issues here: <https://github.com/veripublica/epubveri-plugins/issues>. If the
finding itself looks wrong rather than the plugin, that belongs in
[epubveri](https://github.com/veripublica/epubveri/issues) — and a wrong error
on a good book is the one we most want to hear about.
