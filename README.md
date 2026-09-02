# epubveri-plugins

Editor plugins for [**epubveri**](https://github.com/veripublica/epubveri) — a
pure-Rust, JVM-free EPUB validator. They put epubveri inside the editor you
already use, so validating a book is a menu item rather than a terminal.

| | |
|---|---|
| `sigil/` | plugin for [Sigil](https://sigil-ebook.com/) |
| `client/` | the shared half: fetching and verifying the binary, and reading epubveri's JSON envelope |
| `build.py` | produces one installable zip per editor into `dist/` |

## Installing

Download the zip for your editor from
[**Releases**](https://github.com/veripublica/epubveri-plugins/releases) — not
from this source tree. Both editors install a plugin **from a zip file**, never
from a folder: Sigil's file dialog is titled *Select Plugin Zip Archive* and
accepts `Plugin Files (*.zip)`, and calibre's *Load plugin from file* is the
same.

- **Sigil** — *Plugins → Manage Plugins → Add Plugin*, pick the zip. The
  plugin then appears under *Plugins → Validation → epubveri*.
- On first use it downloads the epubveri binary for your platform from
  epubveri's own releases and verifies it against that release's
  `SHA256SUMS.txt`. Nothing else is installed, and no binary is inside the
  plugin zip.

Building one yourself, if you would rather not take a release:

```
python3 build.py            # writes dist/sigil_epubveri_v<version>.zip
python3 build.py sigil      # just that one
```

`build.py` lives at the root rather than inside `sigil/` because it serves
every editor and because `client/` is shared: the build **copies** it into each
package, since a Sigil plugin is a flat folder and a calibre plugin is a zip
and neither can import a sibling package from elsewhere on disk. That is also
why nothing in `client/` may import from `sigil/` or `calibre/` — the
dependency runs one way, and the build only ever copies in that direction.

## Licensing

**This repository is GPL-3.0-only.** Every folder, including `client/`.

The two facts behind that, because they are not symmetric and it is worth
knowing which is a constraint and which is a choice:

- **calibre requires it.** A calibre plugin imports calibre's own modules at
  runtime (`calibre.gui2.tweak_book.plugin`, `calibre.utils.config`), and
  calibre is GPL-3.
- **Sigil does not.** Its plugin interface — `launcher.py`,
  `bookcontainer.py`, `validationcontainer.py` — is BSD-licensed by Kevin B.
  Hendricks, Doug Massay and John Schember, and a Sigil plugin imports none of
  it (`bk` arrives as an argument). GPL-3 here is a choice, taken for
  consistency across the repository.

### These plugins do not contain epubveri, and that is deliberate

epubveri itself is **AGPL-3.0-only OR a commercial licence**. These plugins run
it as a **subprocess** over its documented JSON envelope and never link it, and
no binary is shipped inside a plugin package — the plugin downloads one from
epubveri's own releases on first use and **verifies it against that release's
`SHA256SUMS.txt`**.

So a plugin package conveys no AGPL code and carries none of the notice or
source-offer obligations that would follow if it did. (The two licences are in
any case explicitly compatible: AGPL-3 §13 and GPL-3 §13 each permit combining
with the other.)

## Contributing

**Unlike the epubveri repository, this one needs no CLA.** epubveri is sold
under a commercial licence as well as the AGPL, so it requires a single
copyright holder; these plugins are not sold, so contributions are welcome
under the GPL-3 on the ordinary terms. Open an issue or a pull request.

## Credit

Doitsu wrote the first epubveri plugins for both Sigil and calibre and proved
the idea; thiago.eec contributed to the calibre one. These are independent
implementations rather than forks — none of their code is used here — but the
concept, and much of what we learned about what an editor integration needs,
came from theirs.
