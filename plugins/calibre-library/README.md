# epubveri library check — a calibre plugin

Validate a **whole calibre library** with [epubveri](https://github.com/veripublica/epubveri),
a fast, JVM-free EPUB validator, and see which defects recur across it.

This is the *library* plugin. There is a separate **editor** plugin in this
repository for Edit Book, and the two work together: this one answers **which**
books have a problem, that one answers **what** the problem is.

> **Status: 0.1.0.** It has run on calibre 9.14 on macOS and nowhere else.
> `minimum_calibre_version` is 6.0 because that is the oldest release it can
> *load* on (`qt.core` arrived with calibre 6); it is not a claim about testing.

## What it shows you, and why it is not a list of books

The obvious report is a list of books with an error count beside each. That
shape was measured against a real 474-book library and dropped, for three
reasons that hold for any library:

* A **won't open / fatal** column would always be empty. epubveri deliberately
  does not escalate a recoverable fault to fatal, so no real book produced one.
* **Error count is anti-correlated with variety at the top.** The books with
  the highest counts trip *one* rule thousands of times — a producer pattern
  repeated once per paragraph — while the most varied book trips seven rules
  with a hundredth of the findings. Sorting by count puts the least interesting
  and most easily fixed book first.
* **Valid / invalid** fails the same way: about half of a real library is
  invalid, and a third of those by one or two findings. "Half your library is
  invalid" teaches nobody anything.

So the report is **one row per defect**, ordered by how many books carry it:

| Message | What it says | Severity | Books | Findings |
|---|---|---|---|---|
| RSC-005 | element "div" is not allowed here | ERROR | 181 | 8 442 |
| OPF-003 | resource is not declared in the manifest | ERROR | 44 | 61 |

Understand one row, fix hundreds of books. Select a row and **Show affected
books** marks them and filters the library view to them; double-clicking a book
there opens it in Edit Book, where the editor plugin shows the findings in
place.

## Using it

* **epubveri** in the toolbar repeats whichever scope you used last. Its menu
  offers **the whole library** or **the selected books**.
* The scan runs as a background job. calibre stays usable, the Jobs panel shows
  progress, and **cancelling still shows what it found** — a scan of three
  thousand books takes about ten minutes and is not thrown away by a change of
  mind.
* Only books with an **EPUB** format are checked. Books without one are counted
  and reported rather than quietly skipped.

### Speed

About **0.2 seconds a book**, so ten minutes for three thousand. epubcheck is
roughly eleven times slower on the same books (measured: 758 s against 69 s
over 385 books), which for a library is the difference between a coffee and an
afternoon. See epubveri's `docs/BENCHMARK.md`.

## What the report ranks

Errors and fatals always. Warnings by default. **Usage notes and advisory
findings are fetched but not ranked by default**, and the difference is
deliberate: this table ranks *defects*, and a usage note names a feature the
book uses rather than anything wrong with it. Ranked in, `CSS-028` (an
`@font-face` declaration) tops the list on any real library and teaches
nothing.

They are one checkbox away in the report window, and the window says how many
findings the current filter is leaving out. Switching a box **re-sorts** the
report; it never re-validates the library.

Advisory (`ADV-*`) findings are epubveri's own: epubcheck says nothing about
them and **they never change a verdict**. A book that passes epubcheck passes
epubveri.

## The validator binary

No epubveri binary ships inside this plugin. On first use it is downloaded from
epubveri's own releases and **verified against that release's
`SHA256SUMS.txt`** before anything is extracted, and its hash is checked again
before every scan.

It lives in `<calibre config>/plugins/epubveri-library-data/`, and it is **this
plugin's own copy** — the editor plugin keeps a separate one. That costs a
second 2.8 MB download and buys three things: a library scan holds the binary
open for ten minutes and **Windows does not allow a running executable to be
overwritten**, so a shared file could be updated out from under a scan; each
plugin stays auditable as one folder; and neither plugin ever has to be
released in step with the other.

Both plugins name the epubveri version they used, so if the two ever drift
apart you can see it rather than having to wonder.

Automatic update checks are hourly at most, never during a scan, and can be
switched off in *Preferences → Plugins → Customize*. They cost 842 bytes.

## Installing

1. Download `epubveri_calibre_library_vX.Y.Z.zip` from the
   [releases](https://github.com/veripublica/epubveri-plugins/releases).
2. calibre → *Preferences → Plugins → Load plugin from file*.
3. Add it to a toolbar if calibre does not (*Preferences → Toolbars*).

Do **not** install with `calibre-customize` while calibre is open: it and the
running GUI write the same file, and the GUI wins.

## Building and testing

```
python3 plugins/calibre-library/build.py
/Applications/calibre.app/Contents/MacOS/calibre-debug \
    plugins/calibre-library/tests/test_plugin.py
```

The tests run inside calibre's own interpreter and read the working tree, not
an installed copy. They hold this plugin's own reasoning — the grouping, the
ordering, the filter, the shared install record — and they cannot see the
toolbar, the Jobs panel, or a library being written to during a scan. Every
defect the sibling plugins have had was found by a person clicking.

## Licence

GPL-3.0-only, like everything in this repository. calibre is GPL-3 and this
plugin imports it, so for this one it is required rather than chosen.

epubveri itself is AGPL-3.0-only OR commercial. This plugin never links it — it
runs it as a subprocess over its documented JSON envelope — and ships no copy
of it, so the package conveys no AGPL code.
