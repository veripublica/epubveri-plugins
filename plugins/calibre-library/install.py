# epubveri library check — getting a verified binary, and sharing it
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Where the epubveri binary lives, and who is allowed to say what it is.

**The binary is shared with the editor plugin; the record of which binary it
is has to be shared with it too, and that is not obvious.** The editor plugin
(0.4.2 and earlier) keeps `binary_sha256` in its own preferences and refuses to
run anything that does not match it — a deliberate guarantee, and the right
one when a plugin owns its copy. Two plugins over one folder break it: the
moment either updates the binary, the other's stored hash is stale and its
next run reports the file as tampered with and validates nothing.

So the record moves next to the thing it describes. `epubveri-data/install.json`
holds the archive hash, the binary hash and the update stamps; both plugins
read it, neither owns it, and an update by one is simply what the other reads.

**Back-compatibility is written, not assumed.** A user may well have editor
plugin 0.4.2 installed today, which reads its own preferences and knows nothing
about this file. Whenever this plugin installs or updates the binary it also
writes the two hash keys into `plugins/epubveri.json`, so that plugin keeps
working. That shim goes away once the editor plugin reads the shared record;
until then, removing it means breaking somebody's editor.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from calibre.constants import config_dir
from calibre.utils.config import JSONConfig

from calibre_plugins.epubveri_library.client import binary as bin_mod
from calibre_plugins.epubveri_library.client import runner

#: How long a recorded update check stays good for. A library scan can run for
#: ten minutes; asking GitHub once at the start of it and not again is the
#: whole intent.
UPDATE_INTERVAL = timedelta(hours=1)
STALE_AFTER = timedelta(days=30)
CHECK_TIMEOUT = 5

RECORD_NAME = 'install.json'

#: The editor plugin's preferences file, written to only by the shim above.
EDITOR_PREFS = 'plugins/epubveri'


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

    The name is `epubveri-data` and matches the editor plugin's, on purpose:
    that is the sharing. It is not `epubveri`, because on Linux and macOS
    Doitsu's calibre plugin writes its own copy of the binary to a **file** of
    exactly that name, and the collision breaks both tools.
    """
    path = os.path.join(config_dir, 'plugins', 'epubveri-data')
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

    Read from disk every time rather than cached: the other plugin may have
    rewritten it since, and a cached copy is precisely the stale hash this
    file exists to prevent.
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


def _tell_editor_plugin(archive_sha, binary_sha):
    """Keep editor plugin 0.4.2 working after we replace the binary.

    It verifies the binary against `binary_sha256` in its own preferences and
    runs nothing on a mismatch. Writing the two keys here is what stops a
    library scan from silently disabling somebody's editor plugin. Harmless
    for a version that has moved to the shared record, which will read the
    record first.
    """
    try:
        prefs = JSONConfig(EDITOR_PREFS)
        prefs['installed_sha256'] = archive_sha
        prefs['binary_sha256'] = binary_sha
    except Exception:                                   # noqa: BLE001
        pass


def _remember(archive_sha, binary_sha):
    stamp = _stamp()
    write_record(installed_sha256=archive_sha, binary_sha256=binary_sha,
                 last_update_check=stamp, last_update_success=stamp)
    _tell_editor_plugin(archive_sha, binary_sha)


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
    and, worse, could replace it underneath itself half way through.
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
