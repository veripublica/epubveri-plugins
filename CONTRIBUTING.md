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

`test_in_sigil.py` is the other half and runs in the same command: it drives
the plugin through **Sigil's own `launcher.py`**, with its `Wrapper` and its
result XML and no window. It needs Sigil installed and skips without it
(`SIGIL_APP=…` points at a non-default install). What only it can see is
whatever is true because Sigil is on the other end — above all that the result
XML **parses**, since Sigil writes our message into an attribute without
escaping it, and one unescaped quote makes Sigil display nothing at all.

## Checking an epubveri release against the plugins

```
scripts/verify-release.py --local /path/to/new/epubveri   # before epubveri's tag
scripts/verify-release.py --published                      # after it
```

**Why this exists.** Since the plugins stopped bundling a binary and started
fetching it from epubveri's releases, an epubveri release changes running
plugin code — every installed copy, at once, with no plugin release. All three
`client/binary.py` files are byte-identical, so a break in the download path
hits all three together.

**The plugin test suites cannot see it.** They build their own envelope
fixtures, which is right for testing display logic and useless here: a real
envelope can change shape underneath a green suite. This drives the real
binary through the real `runner`/`envelope`/`binary` code.

The two modes answer different questions. `--local` diffs **what a plugin
sees** — verdict, per-severity counts, advisory count, the `(code, severity)`
set — between the local build and the currently-published one, so an additive
envelope key correctly shows as no change while a moved count does not.
`--published` drives the downloader at `releases/latest`: asset name,
`SHA256SUMS.txt`, checksum, extraction, one real book.

`--local` refuses to compare two binaries reporting the same version, and says
whether the raw envelopes differ at all before reporting that the plugin view
does not. A pass from an instrument that never ran is the one result worth
nothing.

## Building a package

```
python3 plugins/sigil/build.py        # -> dist/sigil/epubveri_vX.Y.Z.zip
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
