# epubveri-plugins

[**epubveri**](https://github.com/veripublica/epubveri) **checks whether an
EPUB file conforms to the specification** — the job epubcheck does, in pure
Rust with no JVM. It reads a book and reports what is wrong with it. **It never
changes anything.**

These are plugins that run it inside the editors people already use, so
validating the book you are working on is a menu item instead of a terminal.
The editing is the editor's; the verdict is epubveri's.

| plugin | for | status |
|---|---|---|
| [`plugins/sigil`](plugins/sigil) | [Sigil](https://sigil-ebook.com/) | **released — [0.2.0](https://github.com/veripublica/epubveri-plugins/releases/tag/sigil-v0.2.0)** |
| [`plugins/calibre`](plugins/calibre) | [calibre](https://calibre-ebook.com/)'s Edit Book | **released — [0.1.0](https://github.com/veripublica/epubveri-plugins/releases/tag/calibre-v0.1.0)** |

**Each plugin has its own README, its own changelog and its own version.**
Start there: this file is only about the repository.

## Installing

Download the zip from
[**Releases**](https://github.com/veripublica/epubveri-plugins/releases) — not
from this source tree. Both editors install a plugin **from a zip file**, never
from a folder, so there is always a zip to fetch.

Each plugin's README has the steps — they differ, and neither editor forgives
getting it wrong: [Sigil](plugins/sigil/README.md) unpacks the zip and takes
the plugin's folder name from the filename, so **do not rename it**;
[calibre](plugins/calibre/README.md) imports straight out of the zip and never
unpacks it. Releases are tagged per plugin (`sigil-v0.1.1`,
`calibre-v0.1.0`), because the two are versioned independently — the tag says
which editor a release is for, and **GitHub's "Latest" badge only means newest
by date**, not newest for your editor.

**Check what you downloaded** if you like: each release publishes a
`SHA256SUMS.txt` beside the zip.

On first use a plugin downloads the epubveri binary for your platform from
epubveri's own releases and **verifies it against that release's
`SHA256SUMS.txt`**. No plugin package contains a binary.

## How the repository is arranged

```
plugins/          the products — one folder per editor
  sigil/            README, CHANGELOG, its own client/, tests, build.py
  calibre/          the same shape, independently versioned
LICENSE           GPL-3.0-only, for everything here
```

Two rules produced that shape, and both are worth knowing before adding a
third plugin:

**Each plugin is self-contained, and stays that way even when two of them share
a language.** They are applications for different programs, not one thing in
two dialects. Someone auditing the Sigil plugin should read one folder and be
done — no shared directory to hold in their head, nothing copied in at build
time that is invisible in the tree. The cost is that the code which talks to
epubveri exists twice; the alternative was worse, because a calibre plugin
wants calibre's own `JSONConfig`, `iswindows` and directory conventions, so a
shared version would have been watered down to what both editors have or filled
with per-editor branches.

**Each plugin builds itself**, with its own `build.py`. A central script would
have to know every editor's packaging quirks — Sigil wants the plugin folder at
the top of the zip and calibre wants the files themselves — and it would be the
wrong language the day a plugin is not Python.

Built zips are never committed. They are produced from a tag and attached to a
release, with their checksums, so that the zip on a forum thread can be checked
against the source that produced it.

## Licensing

**GPL-3.0-only, everywhere in this repository.** For the calibre plugin that is
a requirement — it imports calibre's own GPL-3 modules. For the Sigil plugin it
is a choice: Sigil's plugin interface (`launcher.py`, `bookcontainer.py`,
`validationcontainer.py`) is BSD-licensed by Kevin B. Hendricks, Doug Massay and
John Schember, and a Sigil plugin imports none of it.

### These plugins do not contain epubveri, and that is deliberate

epubveri itself is **AGPL-3.0-only OR a commercial licence**. These plugins run
it as a **subprocess** over its documented JSON envelope and never link it, and
no binary is shipped inside a plugin package — the user's own machine fetches
one from epubveri's releases and verifies it.

So a plugin package conveys no AGPL code and carries none of the notice or
source-offer obligations that would follow if it did. (The two licences are in
any case explicitly compatible: AGPL-3 §13 and GPL-3 §13 each permit combining
with the other.)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version: **unlike the epubveri
repository, this one needs no CLA**, and contributions are welcome.

## Credit

Doitsu wrote the first epubveri plugins for both Sigil and calibre and proved
the idea; thiago.eec contributed to the calibre one. These are independent
implementations rather than forks — none of their code is used here — but the
concept, and much of what we learned about what an editor integration needs,
came from theirs.
