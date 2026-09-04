# epubveri for calibre — the Edit Book tool
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Validate the book being edited, and put the cursor on what is wrong.

**Read this before changing how the container reaches epubveri.** Two of
calibre's contracts here are not guessable and both were taken from its own
source rather than from its documentation:

* `boss.commit_all_editors_to_container()` must run first. calibre keeps
  unsaved edits in the open editors, not in the container, and its own
  docstring says to call this "before performing any actions on the current
  container". `Boss.check_requested` — Check Book — does exactly this.
* **`container.commit()` may not be used.** For an EPUB 3 book
  `EpubContainer.commit` calls `update_modified_timestamp()`, so merely
  validating would rewrite the book's `dcterms:modified`. This plugin reads
  and reports; it changes nothing. So the container is **cloned** first and
  the clone is committed. `clone_container` links rather than copies, which
  is safe because `get_file_path_for_processing` decouples a file from its
  links before writing to a cloned container, and `clone_data` calls the base
  `Container.commit` rather than `EpubContainer`'s — so no timestamp is
  touched on the book the user is editing.

The other difference from the Sigil plugin is the good kind: **calibre
navigates by line and column**, so nothing here computes a character offset.
Sigil takes an absolute document position, which is where its off-by-one came
from.
"""

import os
import tempfile
import shutil
from datetime import datetime, timedelta, timezone

from calibre.constants import config_dir
from calibre.gui2 import error_dialog
from calibre.gui2.tweak_book.plugin import Tool
from calibre.utils.config import JSONConfig
from qt.core import (QAbstractItemView, QCheckBox, QDockWidget, QLabel,
                     QTimer, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                     QWidget, Qt)

# The plugin's own package, never a bare `from client import ...` with the
# plugin folder pushed onto sys.path: `client` is a name any other plugin
# might also use, and the first one imported would win for both.
from calibre_plugins.epubveri import PLUGIN_VERSION
from calibre_plugins.epubveri.client import binary as bin_mod
from calibre_plugins.epubveri.client import runner
from calibre_plugins.epubveri.client.envelope import EnvelopeError

#: calibre's own store, so the settings live where a calibre user expects them
#: and survive a plugin upgrade.
prefs = JSONConfig('plugins/epubveri')
#: `autoupdate` is spelled exactly as the Sigil plugin spells it in its JSON,
#: so the two never disagree about what the setting is called.
prefs.defaults['autoupdate'] = True
#: Both default to on, so that out of the box calibre and Sigil report the
#: same book identically. The boxes are there to quieten the panel, not to
#: hide findings from someone who does not know they exist.
prefs.defaults['show_usage'] = True
prefs.defaults['show_advisory'] = True

_UPDATE_INTERVAL = timedelta(hours=1)
_STALE_AFTER = timedelta(days=30)
_CHECK_TIMEOUT = 5
_ON_VALUES = frozenset(['yes', 'true', 'on', '1', 'y'])


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _ON_VALUES


def _now():
    """UTC, timezone-aware. `datetime.utcnow()` is deprecated in the Python
    calibre bundles (3.14) and is scheduled for removal."""
    return datetime.now(timezone.utc)


def _stamp():
    """A moment, in the spelling this prefs file already had.

    **Epoch seconds, because the key it goes into is not ours alone.**
    calibre keys a plugin's preferences by the plugin's *name*, and Doitsu's
    calibre plugin is also called `epubveri` — so both plugins read and write
    one `plugins/epubveri.json`. His `last_update_check` is `time.time()`; we
    used to write an ISO string into that same key, and his
    `time.time() - last_checked` then raised `TypeError: unsupported operand
    type(s) for -: 'float' and 'str'` for anyone who ran ours and then his.
    Our own reader was already tolerant, so the damage was one-way and his.
    """
    return _now().timestamp()


def _since(stamp):
    """How long ago `stamp` was, or None if it is missing or unreadable.

    Two spellings are accepted on purpose: the epoch seconds written above,
    and the ISO strings this plugin wrote up to 0.2.0 — a stored value is not
    worth throwing away over a format change.
    """
    if not stamp:
        return None
    if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
        try:
            when = datetime.fromtimestamp(stamp, timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    else:
        try:
            when = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return _now() - when


def _stale_note(allowed=True):
    """One quiet line when the binary has not been checked for a long time.

    A user working offline is not missing anything and should not be told
    about the network. But after a month the copy in use may report something
    that has since been fixed, and then "this is old" is the explanation for a
    finding that looks wrong. It is information, not a warning.
    """
    age = _since(prefs.get('last_update_success'))
    if age is None or age < _STALE_AFTER:
        return None
    days = age.days
    if not allowed:
        return ('this epubveri is %d days old; automatic updates are off'
                % days)
    return ('this epubveri is %d days old — no update check has succeeded '
            'since' % days)


def _integrity_failure(path):
    """Is the binary on disk still the one the release vouched for?

    Verifying at download time proves what arrived, not what runs. Hashing
    2.8 MB costs about 1.8 ms, under one percent of a validation, so there is
    no reason to trust yesterday's answer. A missing stored hash means an
    upgrade from a version that recorded none: trust it once and record it,
    rather than refusing to run a binary that is very probably fine.
    """
    stored = prefs.get('binary_sha256')
    actual = bin_mod.sha256_of(path)
    if not stored:
        prefs['binary_sha256'] = actual
        return None
    if actual == stored:
        return None
    return ('the epubveri binary has changed since it was verified '
            '(expected %s, found %s). It was not run. Delete\n%s\nand '
            'validate again to reinstall a verified copy.'
            % (stored[:16], actual[:16], path))


def _install_failure(exc):
    """A sentence a calibre user can act on rather than a raw exception.

    The last line is the fallback and it names the network, so anything that
    is **not** about the network has to be recognised before it — otherwise a
    problem on the disk arrives dressed as an offline machine, which is
    exactly what 374940 #19 was.
    """
    if isinstance(exc, InstallPathError):
        return str(exc)
    if isinstance(exc, bin_mod.DownloadError):
        return 'epubveri could not be installed: %s' % exc
    return ('epubveri could not be downloaded. The first run needs an '
            'internet connection; after that the plugin works offline. (%s)'
            % exc)


def _update_note(before, after):
    old = bin_mod.parse_version(before)
    new = bin_mod.parse_version(after)

    def fmt(v):
        return '.'.join(str(n) for n in v) if v else None

    if old and new and old != new:
        return 'updated epubveri %s to %s' % (fmt(old), fmt(new))
    if new:
        return 'reinstalled epubveri %s' % fmt(new)
    return 'updated epubveri'


def _data_dir():
    """Where the epubveri binary lives. **Not the plugin's own folder.**

    calibre never unpacks a plugin: it imports straight out of the zip, so
    `os.path.dirname(__file__)` is `.../plugins/epubveri.zip` — a file. The
    first run failed on exactly that, `[Errno 17] File exists`, because the
    installer tried to create a directory over the archive it was running
    from. The Sigil plugin can keep the binary beside itself precisely
    because Sigil does unpack; this is the difference, not an oversight.

    So the binary goes in a directory of our own next to the archive.
    `initialize_plugins` reads calibre's `plugins` config dict rather than
    listing that folder, so a subdirectory there disturbs nothing.

    **The name is `epubveri-data` and not `epubveri`, because `epubveri` is
    taken.** Doitsu's calibre plugin — the one in calibre's plugin index, the
    one with the users — writes its copy of the binary to
    `<config>/plugins/epubveri`, which on Linux and macOS is a **file** with
    exactly the name we wanted for a folder. Read from his 0.0.7 source
    (`epubveri_plugin_dir` + `epubveri_binary_name`), not guessed. That
    collision goes both ways and neither tool can win it:

    * his file is in our way — `os.makedirs` raises `[Errno 17] File exists`,
      which is what PeterT met on his first run (MobileRead 374940 #19);
    * our folder is in his way — his `shutil.copy2` would land the binary
      *inside* it and he would then try to execute a directory.

    So we move. He published first, his plugin is what people already have,
    and a name nobody else uses costs us nothing. Windows was never affected:
    his file is `epubveri.exe` there.
    """
    return _prepare_data_dir(
        os.path.join(config_dir, 'plugins', 'epubveri-data'),
        legacy=os.path.join(config_dir, 'plugins', 'epubveri'))


class InstallPathError(Exception):
    """The folder the validator lives in cannot be created, because a name is
    in the way. The user has to move something; nothing here can."""


def _prepare_data_dir(path, legacy=None):
    """`path` as a directory, or a sentence saying what is occupying it.

    **PeterT met the old version of this on Linux** (MobileRead 374940 #19):
    the first run said "epubveri could not be downloaded. The first run needs
    an internet connection" and carried `[Errno 17] File exists` in brackets.
    His connection was fine — something was already sitting at this path, and
    the plugin blamed the network for a problem on the disk. He worked it out
    himself and called it a false alarm; the message is what was wrong.

    `os.path.isdir` is False both for a plain file **and for a symlink whose
    target is gone**, and `os.makedirs` then raises `EEXIST` for either. So
    the occupied case is separated from the missing one and reported with the
    path in it, and the directory itself is created with `exist_ok=True` —
    two editor windows starting together must not turn the same errno into a
    second, unrelated version of this message.
    """
    if os.path.isdir(path):
        return path
    if legacy is not None and not os.path.lexists(path):
        # A 0.2.0 install kept the binary under the shared name. Moving the
        # folder rather than leaving it does two things at once: this plugin
        # keeps the copy it already verified, and the name is free again for
        # the plugin that owns it — which matters, because his code cannot
        # work while a directory sits there.
        ours = os.path.join(legacy, bin_mod.binary_filename())
        if os.path.isdir(legacy) and os.path.isfile(ours):
            try:
                os.rename(legacy, path)
                return path
            except OSError:
                # Nothing here is worth failing a validation for: fall
                # through and install a fresh copy under the new name.
                pass
    if os.path.exists(path) or os.path.islink(path):
        raise InstallPathError(
            'epubveri keeps its validator in\n%s\nand that name is already '
            'taken by something which is not a folder. Rename or remove it '
            'and validate again. Nothing was installed and nothing was '
            'changed.' % path)
    os.makedirs(path, exist_ok=True)
    return path


def _binary_path():
    return os.path.join(_data_dir(), bin_mod.binary_filename())


def _ensure_binary():
    """The epubveri binary to use, installing or updating it as needed.

    Returns `(path, note)`. `path` is None only when the binary on disk failed
    its integrity check, and then `note` says why; nothing is executed.

    **Nothing here may stop a validation.** A failed update check leaves the
    binary that is already there and records the attempt, so a machine with no
    network makes one failed request an hour rather than one per book.
    """
    path = _binary_path()

    def remember(archive_sha, binary_sha):
        prefs['installed_sha256'] = archive_sha
        prefs['binary_sha256'] = binary_sha
        prefs['last_update_check'] = _stamp()
        prefs['last_update_success'] = prefs['last_update_check']

    if not os.path.isfile(path):
        installed, archive_sha, binary_sha = bin_mod.download_binary(
            _data_dir())
        remember(archive_sha, binary_sha)
        return installed, 'installed epubveri'

    tampered = _integrity_failure(path)
    if tampered:
        return None, tampered

    if not _as_bool(prefs.get('autoupdate')):
        # Chosen, so nothing is attempted and nothing is said about it. The
        # age line still applies: it is about the report, not the network.
        return path, _stale_note(allowed=False)

    age = _since(prefs.get('last_update_check'))
    if age is not None and age < _UPDATE_INTERVAL:
        return path, None

    prefs['last_update_check'] = _stamp()
    try:
        sums = bin_mod.latest_checksums(timeout=_CHECK_TIMEOUT)
        wanted = sums.get(bin_mod.asset_name())
        prefs['last_update_success'] = prefs['last_update_check']
        if wanted and wanted != prefs.get('installed_sha256'):
            before = runner.binary_version(path) or ''
            _p, archive_sha, binary_sha = bin_mod.download_binary(
                _data_dir(), expected=wanted)
            remember(archive_sha, binary_sha)
            after = runner.binary_version(path) or ''
            return path, _update_note(before, after)
    except Exception:                                   # noqa: BLE001
        # Offline, rate-limited, a changed release layout — none of it is a
        # reason to refuse to validate the book in front of us.
        pass
    return path, _stale_note()


def _label(finding):
    """The word in front of a finding, so that no line can be mistaken for
    something epubcheck said."""
    return 'ADVISORY' if finding.is_advisory else finding.severity.upper()


def _shown(finding):
    """The two display switches, and nothing else filters."""
    if finding.is_advisory:
        return _as_bool(prefs.get('show_advisory'))
    if finding.severity == 'usage':
        return _as_bool(prefs.get('show_usage'))
    return True


class ConfigWidget(QWidget):
    """Preferences / Plugins / Customize — what Sigil has nowhere to put.

    Three switches. The first is about **the network rather than the
    version**: someone who clears it is saying "do not use my connection" — a
    metered link, an air-gapped machine, or preference — not "keep me on an
    older validator", which nobody wants from a tool whose releases are mostly
    fixes for wrong errors. What it does not stop is the line saying how old
    the binary is: that is an explanation for a finding that looks wrong, not
    a nag to update.

    The other two only decide what the panel lists. **Both start on**, so the
    same book gets the same report from calibre and from Sigil until someone
    chooses otherwise.
    """

    def __init__(self):
        QWidget.__init__(self)
        layout = QVBoxLayout(self)

        self.check_updates = QCheckBox(
            'Keep epubveri up to date automatically', self)
        self.check_updates.setChecked(_as_bool(prefs.get('autoupdate')))
        self.check_updates.setToolTip(
            'Reads 842 bytes of checksums at most once an hour and installs a '
            'newer epubveri if there is one, verifying it first.\n'
            'Clear this to make the plugin use the network never.')
        layout.addWidget(self.check_updates)

        self.show_usage = QCheckBox('Show usage notes', self)
        self.show_usage.setChecked(_as_bool(prefs.get('show_usage')))
        self.show_usage.setToolTip(
            'Findings epubcheck also reports, but hides unless you pass -u. '
            'They are not errors and never change the verdict.')
        layout.addWidget(self.show_usage)

        self.show_advisory = QCheckBox(
            'Show advisory findings epubcheck does not make', self)
        self.show_advisory.setChecked(_as_bool(prefs.get('show_advisory')))
        self.show_advisory.setToolTip(
            'epubveri’s own ADV-* checks. They never change the verdict '
            'or the exit code: a book that passes epubcheck passes epubveri.')
        layout.addWidget(self.show_advisory)

        note = QLabel(
            'epubveri itself is downloaded once, on first use, and verified '
            'against the release checksums before it is ever run.\nClearing '
            'the display boxes hides those findings from the panel; it does '
            'not change the verdict, which never counted them.', self)
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

    def save_settings(self):
        prefs['autoupdate'] = self.check_updates.isChecked()
        prefs['show_usage'] = self.show_usage.isChecked()
        prefs['show_advisory'] = self.show_advisory.isChecked()


class ResultsPanel(QWidget):
    """The findings, and a way to get to each one. Lives in a dock.

    **Not calibre's Check Book panel**, which cannot be used: `run_checks`
    calls calibre's own checkers directly and takes no plugin, so there is no
    hook to add to it. Reaching into it anyway would mean depending on its
    internals, which is how a plugin breaks on someone else's refactor.

    A dock of our own is as close as a plugin can get, and it is what Doitsu
    asked for (MobileRead 374940 #16), with JSWolf adding that it was more
    than a nitpick (#17). It replaces a non-modal dialog that had the right
    behaviour and the wrong shape: docking, tabbing and a remembered position
    are what a panel gets for free and a floating window never does.
    """

    def __init__(self, tool, parent=None):
        QWidget.__init__(self, parent)
        self.tool = tool

        layout = QVBoxLayout(self)
        # A dock is narrower than the dialog was; the summary has to wrap
        # rather than set the panel's minimum width.
        self.summary = QLabel('', self)
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)

        self.items = QTreeWidget(self)
        self.items.setHeaderLabels(['', 'File', 'Line', 'Message'])
        self.items.setRootIsDecorated(False)
        self.items.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.items.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items.itemActivated.connect(self.go_to)
        self.items.itemDoubleClicked.connect(self.go_to)
        layout.addWidget(self.items)

    def show_results(self, findings, summary):
        """Replace what is displayed. One panel, reused.

        The dialog this replaces was created afresh each run and the old one
        closed, because two non-modal windows would otherwise accumulate and
        the older would describe a book that had since been edited. A dock is
        a single object, so the same guarantee comes from clearing it.
        """
        self.summary.setText(summary)
        self.items.clear()
        for finding in findings:
            item = QTreeWidgetItem(self.items)
            item.setText(0, _label(finding))
            item.setText(1, finding.location or '')
            item.setText(2, str(finding.line) if finding.line else '')
            text = finding.message or ''
            if finding.code:
                text = '%s: %s' % (finding.code, text)
            if finding.is_advisory:
                text += ('  (epubcheck does not report this; the verdict is '
                         'unaffected)')
            item.setText(3, text)
            item.setData(0, Qt.ItemDataRole.UserRole,
                         (finding.location, finding.line, finding.column))
        for column in range(3):
            self.items.resizeColumnToContents(column)

    def go_to(self, item):
        """Open the file and put the cursor on the finding.

        This is what `Boss.check_item_activated` does for calibre's own check
        results, and it is deliberately the same: reuse the editor if the file
        is already open, otherwise ask the boss to open it, then jump.

        **The conventions, read off `TextEdit.go_to_line` rather than
        assumed:** the line is 1-based (`NextBlock, n=lnum - 1` from the
        start, clamped to `blockCount`) and the column is **0-based**
        (`block().position() + col`). epubveri's column is 1-based, hence the
        subtraction. calibre also clamps a column past the end of the line
        back to the end of that line, so the overshoot that moved Sigil's
        cursor onto the following line cannot happen here.
        """
        location, line, column = item.data(0, Qt.ItemDataRole.UserRole)
        if not location:
            return
        from calibre.gui2.tweak_book import editors
        container = self.tool.current_container
        if container is None or location not in container.mime_map:
            return error_dialog(
                self, 'epubveri',
                'The file %s is no longer in the book. Validate again to '
                'refresh these results.' % location, show=True)
        editor = editors.get(location)
        if editor is not None:
            self.tool.boss.gui.central.show_editor(editor)
        else:
            editor = self.tool.boss.edit_file_requested(
                location, None, container.mime_map[location])
        if editor is not None and getattr(editor, 'has_line_numbers', False):
            editor.go_to_line(line or 0, (column or 1) - 1)
            editor.set_focus()



def _package(container, destdir):
    """Write `container` out as an `.epub`, without changing the book.

    **The obvious call is the wrong one.** `EpubContainer.commit` calls
    `update_modified_timestamp()` for an EPUB 3 book, so committing the
    container the user is editing — even to a temporary path — rewrites its
    `dcterms:modified`. Validating would edit the book. So the container is
    cloned and the clone is committed; the timestamp moves on the copy.

    `clone_container` links rather than copies, which is safe:
    `get_file_path_for_processing` decouples a file from its links before
    writing to a cloned container. And `clone_dir` says it plainly — "dest
    must already exist" — so the directory is created here; without that the
    first clone fails on META-INF.

    epubveri takes a packaged file rather than a directory: a decided scope,
    so every tool in this family hands the others the same unit.
    """
    from calibre.ebooks.oeb.polish.container import clone_container
    clone_root = os.path.join(destdir, 'clone')
    os.makedirs(clone_root)
    clone = clone_container(container, clone_root)

    # **Nothing may stamp a read-only packaging**, and cloning alone is not
    # enough to stop it. `EpubContainer.commit` calls
    # `update_modified_timestamp()`, which dirties the OPF, and a dirtied file
    # is re-serialised on the way out rather than copied. calibre's serialiser
    # is not byte-preserving: on one fixture it split
    # `<dc:title>T</dc:title><dc:language>en</dc:language>` onto two lines and
    # wrote `<dc:creator/>` for `<dc:creator></dc:creator>`, so the OPF gained
    # a line and every finding below it was reported one line off — the same
    # defect the Sigil plugin had, arriving by a different route.
    #
    # Neutralising it on this throwaway clone leaves the OPF undirtied, so it
    # is copied verbatim. Measured: with this, every file in the produced
    # `.epub` is byte-identical to the container's, and an edited file is too
    # — `commit_editor_to_container` writes the editor's bytes straight to the
    # container with no parse.
    clone.update_modified_timestamp = lambda *a, **k: None

    epub_path = os.path.join(destdir, 'current.epub')
    clone.commit(epub_path)
    return epub_path


class EpubVeriTool(Tool):
    """One entry in the editor's Plugins menu and toolbar."""

    name = 'epubveri'
    allowed_in_toolbar = True
    allowed_in_menu = True

    #: The name calibre's `saveState` keys the dock's position on. It must
    #: not change: a saved layout that no longer matches loses the position
    #: the user put the panel in.
    DOCK_OBJECT_NAME = 'epubveri-results-dock'
    #: True once this session has put findings in the panel. Read by
    #: `_close_after_restore`, which must never close a panel someone
    #: is reading.
    _validated = False

    def _ensure_dock(self):
        """The results dock, created once and then reused.

        **Created from `create_action`, and the timing is the whole reason.**
        `Main.__init__` runs `create_actions()` — which constructs this tool
        and calls `create_action` — before `create_docks()`, and defers
        `restore_state` to `QTimer.singleShot(0, ...)` at the end. So a dock
        added here exists before `restoreState` runs, and **calibre remembers
        its area, size and visibility for us**; there is nothing of ours to
        store. Adding it later, on the first validation, would put it back in
        the default corner every session.

        **That order holds in calibre 6.0, 7.0, 8.0 and 9.14** — checked in
        each, because `minimum_calibre_version` claims all of them and this
        would fail silently on any release where it did not. The round trip
        itself is a test rather than a claim: move the dock, save the window
        state, build a fresh window and dock, restore, and it comes back where
        it was put — and does not when the objectName is removed.

        `self.gui` is safe this early: `Main.__init__` assigns `self.boss =
        Boss(self)` before `create_actions()`, and `Boss.__init__` sets both
        the module-level `_boss` and `self.gui = parent` before it returns.
        Worth having checked rather than assumed — `QAction(text, None)` is
        legal, so the action this method sits beside would not have complained
        about a `gui` that was not there yet, and `addDockWidget` would.

        **`create_action` is called twice** — once for the toolbar and once
        for the menu, on this same instance — so this is guarded. calibre
        *swallows* an exception from `create_action`: `create_plugin_action`
        prints a traceback to stderr and drops the tool from the menu with
        nothing on screen, so a second dock or a raise here would be close to
        invisible.
        """
        dock = getattr(self, '_dock', None)
        if dock is not None:
            return dock
        dock = QDockWidget('epubveri', self.gui)
        dock.setObjectName(self.DOCK_OBJECT_NAME)   # needed for saveState
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea)
        self._panel = ResultsPanel(self, dock)
        dock.setWidget(self._panel)
        # The area Check Book uses, since that is the panel this one is meant
        # to sit beside. Hidden until the first validation, the way calibre
        # brings up Live CSS.
        self.gui.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, dock)
        dock.close()
        self._dock = dock
        self._close_after_restore()
        return dock

    def _close_after_restore(self):
        """Hidden at startup **even when the last session left it open.**

        `dock.close()` above is not enough on its own. `restoreState` restores
        a dock's visibility along with its area and size, so a session that
        ended with the panel open started the next one with it open — over a
        book nothing had validated yet, and with an empty panel. thiago.eec
        asked for the opposite and Doitsu agreed (MobileRead 374940 #20, #21):
        it should behave like the EPUBCheck and ACE plugins, which show
        nothing until you ask them for something. Those two are dialogs, so
        they get it for free; a dock has to be told.

        **The position is still remembered — only the visibility is not.**
        That is the whole reason this is a second, deferred close rather than
        dropping the `objectName` and giving up on `restoreState`.

        The ordering, which is what makes the two-step timer work rather than
        being a superstition: `Main.__init__` calls `create_actions()` — where
        this dock is built — and only then, at the end, queues
        `QTimer.singleShot(0, self.restore_state)`. Zero timers fire in the
        order they were registered, so the outer one here runs **before**
        `restore_state`, and the inner one it registers goes behind it. If a
        future calibre ever reorders that, the close lands early and the
        behaviour is the one we have today: visible. A wrong guess costs the
        request, not the plugin.

        The `_validated` guard is the other half of that: whatever the timers
        do, a panel showing findings is never closed under the user.
        """
        dock = self._dock

        def close_it():
            if not self._validated:
                dock.close()

        QTimer.singleShot(0, lambda: QTimer.singleShot(0, close_it))

    def _action_icon(self):
        """The toolbar icon, or a null one where there is no plugin zip.

        `get_icons` is not imported: calibre's zip loader injects it into every
        module of a plugin it loads (`zipplugin.py`, `module.__dict__`), bound
        to that plugin's archive. Given one name it returns a `QIcon` read from
        the zip — so `plugin.png` has to be at the archive root, which is where
        `build.py` puts everything.

        Under the tests there is no zip and no injection, so this looks the
        name up rather than trusting it to exist. Calling it blind would raise
        `NameError` inside `create_action`, and calibre **swallows** that:
        `create_plugin_action` prints a traceback to stderr and drops the tool
        from the menu with nothing on screen.
        """
        from qt.core import QIcon
        get = globals().get('get_icons')
        return get('plugin.png') if get is not None else QIcon()

    def create_action(self, for_toolbar=True):
        from qt.core import QAction
        self._ensure_dock()
        action = QAction(self._action_icon(), 'Validate with epubveri',
                         self.gui)
        action.triggered.connect(self.validate)
        if not for_toolbar:
            self.register_shortcut(action, 'epubveri-validate')
        return action

    def _write_book(self, destdir):
        """The book as the user currently has it, as a real `.epub` file.

        Unsaved edits live in the open editors rather than in the container,
        so they are committed first — calibre's own docstring for this method
        says to call it before acting on a container, and `check_requested`
        does. The packaging itself is `_package`, which takes a container and
        no editor, so the part that must not touch the book can be tested
        without a GUI.
        """
        self.boss.commit_all_editors_to_container()
        return _package(self.current_container, destdir)

    def validate(self):
        if self.current_container is None:
            return error_dialog(self.gui, 'epubveri', 'No book is open.',
                                show=True)

        try:
            binary, update_note = _ensure_binary()
        except Exception as exc:                        # noqa: BLE001
            return error_dialog(self.gui, 'epubveri', _install_failure(exc),
                                show=True)
        if binary is None:
            # Integrity check failed. Nothing is executed.
            return error_dialog(self.gui, 'epubveri', update_note, show=True)

        tmpdir = tempfile.mkdtemp(prefix='epubveri-calibre-')
        try:
            try:
                epub_path = self._write_book(tmpdir)
            except Exception as exc:                    # noqa: BLE001
                return error_dialog(
                    self.gui, 'epubveri',
                    'The book could not be packaged for validation: %s' % exc,
                    show=True)
            try:
                envelope = runner.run_epubveri(binary, epub_path)
            except EnvelopeError as exc:
                return error_dialog(self.gui, 'epubveri', str(exc), show=True)
            except Exception as exc:                    # noqa: BLE001
                return error_dialog(self.gui, 'epubveri',
                                    'epubveri failed to run: %s' % exc,
                                    show=True)
            if envelope.could_not_read:
                return error_dialog(
                    self.gui, 'epubveri',
                    'epubveri could not read the book: %s'
                    % (envelope.error or 'no reason given'), show=True)
            self._show(envelope, update_note)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _show(self, envelope, update_note):
        shown = [f for f in envelope.findings if _shown(f)]
        verdict = 'VALID' if envelope.is_valid else 'NOT VALID'
        # The verdict quotes only errors, fatals and warnings, because that is
        # what decides it and what epubcheck would print. Usage notes and
        # advisories count towards neither, whether or not they are listed.
        # Both versions are named (Doitsu, MobileRead 374939 #21, "for
        # debugging purposes"). epubveri's says which validator produced the
        # findings; the plugin's says which code turned them into these rows,
        # and most of what has gone wrong in these plugins so far was on this
        # side of that line. `PLUGIN_VERSION` is derived from the tuple
        # calibre itself reads, so there is no second copy to bump.
        summary = 'epubveri %s (plugin %s) — %s (%d error(s), %d warning(s))' % (
            envelope.version, PLUGIN_VERSION, verdict,
            envelope.count('error') + envelope.count('fatal'),
            envelope.count('warning'))
        advisory = sum(1 for f in envelope.findings if f.is_advisory)
        # ADV-*/NEXT-* are emitted AT usage severity, so the envelope's usage
        # count already contains them; subtract or they are counted twice.
        usage = envelope.count('usage') - advisory
        hidden = len(envelope.findings) - len(shown)
        extra = []
        if usage > 0:
            extra.append('%d usage note(s)' % usage)
        if advisory:
            extra.append('%d advisory finding(s) epubcheck does not make'
                         % advisory)
        if extra:
            summary += ('; also found: %s — neither affects the verdict'
                        % ', '.join(extra))
        if hidden:
            # Never silently shorter than the book deserves: if a switch is
            # hiding something, the panel says so and where to turn it back on.
            summary += ('\n%d finding(s) are not listed because of the '
                        'display settings (Preferences → Plugins → Customize).'
                        % hidden)
        if update_note:
            summary += '\n[%s]' % update_note

        # One dock, cleared and refilled. The dialog this replaces had to
        # close its predecessor by hand or validating three times left three
        # windows, two of them describing a book that had since been edited.
        dock = self._ensure_dock()
        self._validated = True
        self._panel.show_results(shown, summary)
        dock.show()
        dock.raise_()
