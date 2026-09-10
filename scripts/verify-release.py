#!/usr/bin/env python3
# epubveri-plugins — release gate
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Check an epubveri release against the three plugins **before** users meet it.

Since the plugins stopped bundling a binary and started fetching it from
epubveri's own releases, an epubveri release is a change to running plugin
code — for every installed copy, at once, without a plugin release. All three
`client/binary.py` files are byte-identical, so anything that breaks the
download breaks all three together.

Two moments, two different risks, and one flag each:

  --local <path>    BEFORE the tag. Runs the plugins' own runner and envelope
                    parser over a shelf of books with the local build and with
                    the currently-published one, and diffs *what the plugin
                    sees* — verdict, per-severity counts, advisory count, and
                    the (code, severity) set. Catches an envelope change that
                    reaches a plugin. The plugins' unit tests cannot: they
                    build their own fixtures, so a real envelope could change
                    shape underneath a green suite.

  --published       AFTER the tag. Drives the plugins' own `binary.py` against
                    the live `releases/latest`: asset name, SHA256SUMS.txt
                    listing, checksum verification, extraction, and one real
                    book through the runner. Catches a packaging change — a
                    renamed asset, a missing checksums file, a release not
                    marked latest.

Both modes prove they are not vacuous before reporting a pass: `--local`
refuses a comparison of two identical binaries and shows that the raw JSON
really differs, because a "no change" result from an instrument that never ran
is the failure this family keeps re-learning.

Usage:
    scripts/verify-release.py --published
    scripts/verify-release.py --local ~/.cargo-target/release/epubveri
    scripts/verify-release.py --local <path> --books 60 --shelf ~/…/ebook-shelf
"""

import argparse
import glob
import importlib.util
import os
import subprocess
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS = ("sigil", "calibre", "calibre-library")
DEFAULT_SHELF = os.path.expanduser("~/Documents/Projects/ebook-shelf")

RED, GREEN, BOLD, OFF = "\033[31m", "\033[32m", "\033[1m", "\033[0m"


def load(which):
    """Import one plugin's client package without installing anything."""
    base = os.path.join(ROOT, "plugins", which, "client")
    pkg = "cl_" + which.replace("-", "_")
    mod = types.ModuleType(pkg)
    mod.__path__ = [base]
    sys.modules[pkg] = mod
    for name in ("envelope", "binary", "runner"):
        spec = importlib.util.spec_from_file_location(
            pkg + "." + name, os.path.join(base, name + ".py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules[pkg + "." + name] = m
        spec.loader.exec_module(m)
    return sys.modules[pkg + ".binary"], sys.modules[pkg + ".runner"]


def view(runner, binary, book):
    """Exactly what a plugin surfaces to its user, as a comparable tuple.

    Deliberately not the raw JSON: the question is not "did the envelope
    change" — 0.14.0 changed it on purpose — but "did anything a plugin *reads*
    change". Additive keys are invisible here, which is the correct answer.
    """
    env = runner.run_epubveri(binary, book, advisory=True)
    advisory = sum(1 for f in env.findings if getattr(f, "advisory_basis", None))
    return (
        env.input_status, env.is_valid, env.could_not_read,
        env.count("fatal"), env.count("error"), env.count("warning"),
        env.count("info"), env.count("usage"), advisory, len(env.findings),
        tuple(sorted((f.code, f.severity) for f in env.findings)),
    )


def books_from(shelf, limit):
    found = sorted(glob.glob(os.path.join(shelf, "*", "*.epub")))
    if not found:
        sys.exit("no books under %s — pass --shelf" % shelf)
    return found[:limit]


def mode_local(args):
    """A/B the local build against the published one, through plugin eyes."""
    binary_mod, _ = load("sigil")
    with tempfile.TemporaryDirectory() as tmp:
        print("fetching the currently-published binary (what users run today)…")
        published, _, _ = binary_mod.download_binary(tmp)

        def version(path):
            return subprocess.run([path, "-V"], capture_output=True,
                                  text=True).stdout.strip()

        vp, vl = version(published), version(args.local)
        print("  published: %s\n  local:     %s" % (vp, vl))
        if vp == vl:
            sys.exit("%sboth sides report the same version — this comparison "
                     "would prove nothing. Bump, or point --local elsewhere.%s"
                     % (RED, OFF))

        book = books_from(args.shelf, 1)[0]
        raw = [subprocess.run([b, "--format", "json", "-u", "--advisory",
                               "-i", book], capture_output=True, text=True).stdout
               for b in (published, args.local)]
        if raw[0] == raw[1]:
            print("  note: raw envelopes are identical too — nothing changed "
                  "in the output at all.")
        else:
            print("  raw envelopes differ, so the change does reach a plugin's "
                  "input. Now: does anything a plugin READS differ?")

        books = books_from(args.shelf, args.books)
        bad = 0
        for which in PLUGINS:
            _, runner = load(which)
            diffs = []
            for b in books:
                before, after = view(runner, published, b), view(runner, args.local, b)
                if before != after:
                    diffs.append((b, before, after))
            if diffs:
                bad += 1
                print("%s  FAIL %-16s %d of %d books differ%s"
                      % (RED, which, len(diffs), len(books), OFF))
                for b, before, after in diffs[:3]:
                    print("       %s" % os.path.basename(b))
                    for i, (x, y) in enumerate(zip(before, after)):
                        if x != y:
                            print("         field %d: %r -> %r" % (i, x, y))
            else:
                print("%s  ok   %-16s %d books, identical%s"
                      % (GREEN, which, len(books), OFF))
        return bad


def mode_published(args):
    """Drive each plugin's own downloader against releases/latest."""
    book = books_from(args.shelf, 1)[0]
    bad = 0
    for which in PLUGINS:
        binary_mod, runner = load(which)
        try:
            name = binary_mod.asset_name()
            sums = binary_mod.latest_checksums()
            expected = sums.get(name)
            if not expected:
                raise AssertionError(
                    "%s lists %d assets and none is %s"
                    % (binary_mod.CHECKSUMS_NAME, len(sums), name))
            with tempfile.TemporaryDirectory() as tmp:
                path, _archive_sha, _bin_sha = binary_mod.download_binary(tmp)
                env = runner.run_epubveri(path, book, advisory=True)
            print("%s  ok   %-16s %s | %d assets listed | ran a book: %s, "
                  "%d findings | %s%s"
                  % (GREEN, which, name, len(sums), env.input_status,
                     len(env.findings), env.tool_version, OFF))
        except Exception as exc:                      # noqa: BLE001 — reported
            bad += 1
            print("%s  FAIL %-16s %s: %s%s"
                  % (RED, which, type(exc).__name__, exc, OFF))
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--local", metavar="PATH",
                   help="pre-tag: A/B this build against the published one")
    g.add_argument("--published", action="store_true",
                   help="post-tag: drive the plugins' downloader at releases/latest")
    ap.add_argument("--shelf", default=DEFAULT_SHELF)
    ap.add_argument("--books", type=int, default=60)
    args = ap.parse_args()

    print("%s%s%s" % (BOLD,
                      "epubveri release gate — the three plugins",
                      OFF))
    bad = mode_local(args) if args.local else mode_published(args)
    if bad:
        print("\n%sNOT READY%s — %d of %d plugins would be affected."
              % (RED, OFF, bad, len(PLUGINS)))
        return 1
    print("\n%sall three plugins unaffected%s" % (GREEN, OFF))
    return 0


if __name__ == "__main__":
    sys.exit(main())
