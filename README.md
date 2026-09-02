# epubveri-plugins

Editor plugins for [**epubveri**](https://github.com/veripublica/epubveri) — a
pure-Rust, JVM-free EPUB validator. They put epubveri inside the editor you
already use, so validating a book is a menu item rather than a terminal.

| | |
|---|---|
| `sigil/` | plugin for [Sigil](https://sigil-ebook.com/) |
| `client/` | the shared half: fetching and verifying the binary, and reading epubveri's JSON envelope |
| `build.py` | produces one installable zip per editor into `dist/` |

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
