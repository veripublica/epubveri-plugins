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

## The two switches

Both are off by default, matching epubveri's own command line and epubcheck's
behaviour. Both are in the plugin's preferences, and every run tells you when
something was hidden.

| | what it adds |
|---|---|
| **Show usage notes** | `usage`-severity findings — things worth knowing that are not defects, like an unreferenced image. epubcheck hides these too unless you pass `-u`. |
| **Advisory checks** | `ADV-*` and `NEXT-*`: opinions epubcheck does not hold. `NEXT-*` becomes an ordinary error once epubcheck catches up with the specification; `ADV-*` is where no specification says anything but the book is still probably wrong. **Neither ever changes the verdict or the exit code.** |

Both are **off** because the report should look the way epubcheck's does until
you ask for more — an extra finding that arrives unasked is indistinguishable
from a wrong one to anyone comparing the two tools.

But the plugin runs epubveri with both on and filters at display, so it can
tell you what it hid *about your book* rather than leaving you to find a
checkbox:

```
epubveri 0.13.3 — NOT VALID (2 error(s), 0 warning(s));
hidden: 1 usage note(s), 1 advisory finding(s) epubcheck does not make
```

Switching either on costs nothing — the book is not validated again.

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
