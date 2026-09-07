# epubveri library — getting a verified binary, and sharing it
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Where the epubveri binary lives, and why it is this plugin's alone.

**This plugin keeps its own copy of the validator, and does not share the
editor plugin's.** That was decided the other way first, on the grounds that
the binary is epubveri's rather than any plugin's. Three things say otherwise,
and the first is the one that settles it:

  * **A running executable cannot be replaced on Windows.** A library scan runs
    the binary continuously for ten minutes. Share the file, and the editor
    plugin's hourly update check can fire in the middle of that and try to
    overwrite it — a sharing violation, reported by the code below as a network
    problem, on the platform three quarters of these downloads go to. Two
    folders make the race impossible rather than unlikely.
  * **It is the rule this repository already committed to.** Every plugin here
    is self-contained so that auditing one means reading one folder. Sharing
    the binary broke that, and paid for it with a shim that wrote into *another
    plugin's* preferences file to keep it working.
  * **It keeps the editor plugin out of it entirely.** No coordinated release,
    no migration, nothing to keep in step.

What sharing bought was one 2.8 MB download instead of two and one update check
instead of two, neither of which is worth any of the above. Its one real
advantage was that the two plugins could never disagree about a book, and that
survives well enough: both name the epubveri version they used in their own
summary line, so a divergence is visible rather than silent, and both follow
`releases/latest` on the same hourly clock.

**The install record lives beside the binary** (`install.json`) rather than in
this plugin's preferences. It describes the file, so it belongs with the file:
delete the folder and the two go together, and there is no way for a recorded
hash to describe a binary that is no longer there.
"""

import json
import json
import os
from datetime import datetime, timedelta, timezone

from calibre.constants import config_dir

from calibre_plugins.epubveri_library.client import binary as bin_mod
from calibre_plugins.epubveri_library.client import runner

#: How long a recorded update check stays good for. A library scan can run for
#: ten minutes; asking GitHub once at the start of it and not again is the
#: whole intent.
UPDATE_INTERVAL = timedelta(hours=1)
STALE_AFTER = timedelta(days=30)
CHECK_TIMEOUT = 5

RECORD_NAME = 'install.json'


class InstallPathError(Exception):
    """The folder the validator lives in cannot be created, because a name is
    in the way. The user has to move something; nothing here can."""


def _now():
    """UTC, timezone-aware. `datetime.utcnow()` is deprecated in the Python
    calibre bundles (3.14) and is scheduled for removal."""
    return datetime.now(timezone.utc)


def _stamp():
    return int(_now().timestamp())


def since(value):
    """How long ago a recorded stamp was, or None if there is not one."""
    if value in (None, ''):
        return None
    try:
        when = datetime.fromtimestamp(float(value), timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None
    return _now() - when


def data_dir():
    """Where the epubveri binary lives. **Not the plugin's own folder.**

    calibre never unpacks a plugin: it imports straight out of the zip, so
    `os.path.dirname(__file__)` is `.../plugins/epubveri_library.zip` — a file,
    and creating a directory over it fails with `[Errno 17] File exists`.

    The name is this plugin's own. Not `epubveri-data`, which is the editor
    plugin's — see the note at the top of this file for why the two are
    separate. And not `epubveri`, because on Linux and macOS Doitsu's calibre
    plugin writes its own copy of the binary to a **file** of exactly that
    name, and the collision breaks both tools in both directions.
    """
    path = os.path.join(config_dir, 'plugins', 'epubveri-library-data')
    if os.path.isdir(path):
        return path
    if os.path.exists(path) or os.path.islink(path):
        # `os.path.isdir` is False both for a plain file and for a symlink
        # whose target is gone, and `makedirs` raises EEXIST for either. Say
        # which path is occupied rather than blaming the network, which is the
        # mistake the editor plugin shipped once (MobileRead 374940 #19).
        raise InstallPathError(
            'epubveri keeps its validator in\n%s\nand that name is already '
            'taken by something which is not a folder. Rename or remove it '
            'and scan again. Nothing was installed and nothing was changed.'
            % path)
    os.makedirs(path, exist_ok=True)
    return path


def binary_path():
    return os.path.join(data_dir(), bin_mod.binary_filename())


def _record_path():
    return os.path.join(data_dir(), RECORD_NAME)


def read_record():
    """The shared install record, or an empty dict.

    Read from disk every time rather than cached. Nothing else writes it now,
    but two calibre windows share one process and one config directory, and a
    cached copy is exactly the stale hash that would refuse to run a perfectly
    good binary.
    """
    try:
        with open(_record_path(), encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_record(**fields):
    """Merge `fields` into the shared record.

    Written whole and replaced, because the file is 200 bytes and a partial
    write of it would be a hash nobody can match.
    """
    data = read_record()
    data.update(fields)
    path = _record_path()
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        # A record we cannot write costs an extra update check, nothing more.
        try:
            os.remove(tmp)
        except OSError:
            pass
    return data


def _remember(archive_sha, binary_sha):
    stamp = _stamp()
    write_record(installed_sha256=archive_sha, binary_sha256=binary_sha,
                 last_update_check=stamp, last_update_success=stamp)


def integrity_failure(path):
    """Is the binary on disk still the one the release vouched for?

    Verifying at download time proves what arrived, not what runs; hashing
    2.8 MB costs about 1.8 ms. A missing recorded hash means either a first
    run under this scheme or an upgrade from a plugin that recorded none
    elsewhere: trust it once and record it, rather than refusing to run a
    binary that is very probably fine.
    """
    record = read_record()
    stored = record.get('binary_sha256')
    actual = bin_mod.sha256_of(path)
    if not stored:
        write_record(binary_sha256=actual)
        return None
    if actual == stored:
        return None
    return ('the epubveri binary has changed since it was verified '
            '(expected %s, found %s). It was not run. Delete\n%s\nand scan '
            'again to reinstall a verified copy.'
            % (stored[:16], actual[:16], path))


def stale_note(allowed=True):
    """One quiet line when the binary has not been checked for a long time.

    A user working offline is not missing anything and should not be told
    about the network. After a month, though, "this copy is old" is the
    explanation for a finding that looks wrong.
    """
    age = since(read_record().get('last_update_success'))
    if age is None or age < STALE_AFTER:
        return None
    if not allowed:
        return ('this epubveri is %d days old; automatic updates are off'
                % age.days)
    return ('this epubveri is %d days old — no update check has succeeded '
            'since' % age.days)


def install_failure(exc):
    """A sentence a calibre user can act on rather than a raw exception.

    The last line is the fallback and it names the network, so anything that
    is **not** about the network has to be recognised before it — otherwise a
    problem on the disk arrives dressed as an offline machine.
    """
    if isinstance(exc, InstallPathError):
        return str(exc)
    if isinstance(exc, bin_mod.DownloadError):
        return 'epubveri could not be installed: %s' % exc
    return ('epubveri could not be downloaded. The first run needs an '
            'internet connection; after that the plugin works offline. (%s)'
            % exc)


def update_note(before, after):
    old = bin_mod.parse_version(before)
    new = bin_mod.parse_version(after)

    def fmt(version):
        return '.'.join(str(n) for n in version) if version else None

    if old and new and old != new:
        return 'updated epubveri %s to %s' % (fmt(old), fmt(new))
    if new:
        return 'reinstalled epubveri %s' % fmt(new)
    return 'updated epubveri'


def ensure_binary(autoupdate=True, status=None):
    """The epubveri binary to use, installing or updating it as needed.

    Returns `(path, note)`. `path` is None only when the binary on disk failed
    its integrity check, and then `note` says why; nothing is executed.

    **Called once per scan, not once per book.** The editor plugin validates
    one book at a time and can afford to ask on every run; a library scan of
    three thousand books would otherwise hash the binary three thousand times
    and, worse, could replace it underneath itself half way through — which on
    Windows would not even be allowed, the file being open for execution.
    """
    path = binary_path()

    def say(message):
        if status is not None and message:
            status(message)

    if not os.path.isfile(path):
        say('downloading epubveri (first run)')
        installed, archive_sha, binary_sha = bin_mod.download_binary(data_dir())
        _remember(archive_sha, binary_sha)
        return installed, 'installed epubveri'

    tampered = integrity_failure(path)
    if tampered:
        return None, tampered

    if not autoupdate:
        # Chosen, so nothing is attempted and nothing is said about it. The
        # age line still applies: it is about the report, not the network.
        return path, stale_note(allowed=False)

    record = read_record()
    age = since(record.get('last_update_check'))
    if age is not None and age < UPDATE_INTERVAL:
        return path, None

    write_record(last_update_check=_stamp())
    try:
        say('checking for a newer epubveri')
        sums = bin_mod.latest_checksums(timeout=CHECK_TIMEOUT)
        wanted = sums.get(bin_mod.asset_name())
        write_record(last_update_success=_stamp())
        if wanted and wanted != read_record().get('installed_sha256'):
            before = runner.binary_version(path) or ''
            say('downloading a newer epubveri')
            _path, archive_sha, binary_sha = bin_mod.download_binary(
                data_dir(), expected=wanted)
            _remember(archive_sha, binary_sha)
            after = runner.binary_version(path) or ''
            note = update_note(before, after)
            say(note)
            return path, note
    except Exception:                                   # noqa: BLE001
        # Offline, rate-limited, a changed release layout — none of it is a
        # reason to refuse to scan the library in front of us.
        pass
    return path, stale_note()
