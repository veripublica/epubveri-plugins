# Contributing

Contributions are welcome, and **this repository needs no CLA** — which is
worth saying plainly, because its sibling does.

[epubveri](https://github.com/veripublica/epubveri) is dual-licensed, AGPL-3.0
or commercial, and selling a commercial licence requires one copyright holder,
so it cannot merge outside code until a contributor agreement exists. These
plugins are not sold. They are GPL-3.0-only, they stay that way, and a pull
request here is an ordinary pull request.

You keep your copyright. By opening a pull request you licence your work under
the GPL-3.0, which is what the rest of the repository is under.

## Before you open a pull request

**Say what you measured, not what you expect.** A change that fixes a crash
should say which input produced it. A change to how findings are presented
should say what a real book looked like before and after. This applies to us
too; it is how the sibling project is written and it is why its own bugs get
found.

**Keep the plugins apart.** Nothing in `plugins/sigil/` may import from
`plugins/calibre/` or the other way round, and neither may grow a shared
directory above them. They are applications for different programs that happen
to share a language. The duplication is deliberate — see the repository README
for what the alternative cost.

**A plugin owns its own packaging.** If you add an editor, it gets its own
folder, its own `README.md`, its own `CHANGELOG.md`, its own version in
whatever file that editor reads, and its own `build.py`. Nothing at the root
should have to learn about it.

**No binary in a package.** A plugin downloads the epubveri binary from
epubveri's own releases and verifies it against that release's
`SHA256SUMS.txt`. Never bundle it: a GPL-3 package must not carry AGPL code,
and the checksum is the only reason the user can trust what arrived.

## Running the tests

```
EPUBVERI_BINARY=/path/to/epubveri python3 -m unittest discover -s plugins/sigil/tests
```

Without `EPUBVERI_BINARY` the tests that need a validator skip rather than
fail, so a missing binary does not look like a broken change.

The tests drive the plugin against a fake editor container. Three of them exist
because those failures are silent otherwise: that the temporary `.epub` is a
valid OCF container (`mimetype` first and stored — get it wrong and every run
reports a packaging error the book does not have), that a full
container-relative path reaches the editor rather than a basename, and that the
display switches do what their names say.

## Building a package

```
python3 plugins/sigil/build.py        # -> dist/sigil_epubveri_vX.Y.Z.zip
```

`dist/` is not committed. Release zips are built from a tag and published with
their checksums, so that the file on a forum thread can be checked against the
source it came from.

## Reporting a problem

An issue about the plugin — it crashed, it put the cursor in the wrong place,
the download failed — belongs here.

An issue about a **finding** — epubveri reported something that is not wrong,
or missed something that is — belongs in
[epubveri](https://github.com/veripublica/epubveri/issues) instead. A wrong
error on a good book is the report that project most wants; every one it has
had came from a user rather than from its own test suite.
