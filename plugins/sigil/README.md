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
epubveri's own releases and keeps it beside the plugin. A download of about
1.1 MB, 2.8 MB on disk, once. Nothing else is installed, and the plugin zip
contains no binary.

**It is verified before every run, not only when it arrives.** The archive is
checked against that release's `SHA256SUMS.txt` on the way in, and the
binary's own checksum is recorded and compared each time it is about to be
used — 1.8 ms for 2.8 MB, under one percent of a validation. If the file has
changed since it was verified, the plugin says so and **runs nothing**:
verifying at download proves what arrived, not what runs.

**After that it keeps itself current.** At most once an hour it reads the
release's `SHA256SUMS.txt` — 842 bytes — and compares one line against the hash
it stored when it installed. If they differ it fetches the new archive,
verifies it, and says so in the summary line. There is nothing to click and
nothing to reinstall.

Comparing checksums rather than version numbers is smaller than asking GitHub's
API (31 KB of JSON, and rate-limited), and stricter: it also notices an archive
re-uploaded under the same tag, or a local copy that has been replaced. If the
machine is offline the check fails quietly and the copy you have is used —
nothing about updating can stop a validation.

Why it bothers: epubveri ships often, and almost every recent release fixed a
*wrong* error on a valid book. An old copy is one that keeps telling you
something untrue.

## What you will see

Findings land in Sigil's validation panel under **File**, **Line** and
**Offset**. The offset is a position in the file rather than a column, which is
what Sigil uses to put the cursor on the character rather than at the start of
the line.

The last line of every run is a summary: which version validated the book, the
verdict, and — when there are any — how many usage notes and advisory findings
are in the list above it, neither of which decides the verdict.

```
epubveri 0.13.3 (plugin 0.2.0) — NOT VALID (2 error(s), 0 warning(s));
also listed: 1 usage note(s), 1 advisory finding(s) epubcheck does not make
             — neither affects the verdict
```

Two versions, because two things can be wrong: epubveri's names the validator
that produced the findings, the plugin's names the code that turned them into
these rows. Quote the whole line when reporting anything.

## What is in the report, and what decides the verdict

**Everything epubveri found is listed by default.** You can switch categories
off (see *Settings* below), and nothing is switched off for you.

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

## Settings

Sigil gives a plugin no settings screen — Manage Plugins lists a plugin's name,
version and platforms and nothing else — so these live in a file:

```
<Sigil preferences>/plugins_prefs/epubveri/epubveri.json
```

The plugin writes it on its first run, with every setting at its default, so
the file shows you which choices exist:

```json
{
  "autoupdate": true,
  "show_usage": true,
  "show_advisory": true,
  "show_summary": true
}
```

| setting | `false` means |
|---|---|
| `show_usage` | `USAGE` lines are not listed |
| `show_advisory` | `ADVISORY` lines are not listed |
| `show_summary` | the last line is not written |
| `autoupdate` | nothing is ever requested over the network |

Three things are worth knowing before you change any of them.

**A category you hide is still counted.** The summary says
`1 usage note(s) hidden by your settings` rather than saying nothing, so a
panel with no usage notes never looks the same as a panel whose usage notes
were filtered. It is also the only place these settings can be discovered, so
switching them off does not hide the fact that they exist.

**Hiding changes the report, never the run.** epubveri is asked for everything
on every run, so the counts in the summary describe the book rather than your
settings.

**Anything that is not clearly a no is read as yes** — `false`, `no`, `off`,
`0` all hide; a typo shows. That is deliberately the opposite of `autoupdate`,
where anything unclear is read as *no*: there the switch spends your
connection, so a misread must not use it; here the switch hides findings, so a
misread must not hide them.

`show_summary: false` has one exception: if there is nothing else in the panel,
the summary is written anyway. Sigil runs this plugin on its own, and an empty
panel is exactly what a plugin that failed to run produces — "your book is
clean" is the one message worth not losing.

## If something goes wrong

- **Working offline?** Once the binary is installed the plugin never needs the
  network again. The hourly check fails silently and the copy you have is used
  — no error, and nothing missing from the report. Measured over 144
  validations across three days with no network: **zero warnings**. The one
  cost is a connection that accepts and then goes nowhere (a captive portal, a
  firewall that drops rather than refuses), which spends five seconds once an
  hour before giving up.
- **Do not want it touching the network at all?** Set `"autoupdate": false`
  in the settings file described above. Nothing is then requested, ever, and
  nothing is said about it. Anything that is not clearly a yes — `false`,
  `no`, `off`, `0`, or a typo — is read as no, because the one thing this
  switch must never do is use your connection when you asked it not to. (The
  calibre plugin has a checkbox for the same setting.)
- **After a month offline** the summary adds one line: *"this epubveri is 45
  days old and could not be checked for updates"*. Not an error and not a
  warning — the validator works. It is there because a copy that old may
  report something that has since been fixed, so if a finding looks wrong,
  that line is the first thing to suspect. It appears whether checks are off
  by choice or by circumstance — it is about the report, not the network.
- **The first run does need the network**, because there is no binary yet. If
  it cannot download one it says so and validates nothing — there is nothing to
  validate with.
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
