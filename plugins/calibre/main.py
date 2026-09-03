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
from qt.core import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox,
                     QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                     QWidget, Qt)

# The plugin's own package, never a bare `from client import ...` with the
# plugin folder pushed onto sys.path: `client` is a name any other plugin
# might also use, and the first one imported would win for both.
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


def _since(stamp):
    """How long ago `stamp` was, or None if it is missing or unreadable."""
    if not stamp:
        return None
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
    """A sentence a calibre user can act on rather than a raw exception."""
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
    """
    path = os.path.join(config_dir, 'plugins', 'epubveri')
    if not os.path.isdir(path):
        os.makedirs(path)
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
        prefs['last_update_check'] = _now().isoformat()
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

    prefs['last_update_check'] = _now().isoformat()
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


class ResultsDialog(QDialog):
    """The findings, and a way to get to each one.

    calibre's own Check Book panel cannot be used: `run_checks` calls
    calibre's checkers directly and takes no plugin, so there is no hook to
    add to it. A dialog of our own is the honest alternative — reaching into
    that panel would mean depending on its internals, which is how a plugin
    breaks on someone else's refactor.

    Non-modal on purpose: activating a row moves the editor behind it, and a
    modal dialog would make that useless.
    """

    def __init__(self, tool, findings, summary):
        QDialog.__init__(self, tool.gui)
        self.tool = tool
        self.setWindowTitle('epubveri')
        self.setWindowFlag(Qt.WindowType.Window)
        self.resize(900, 500)

        layout = QVBoxLayout(self)
        self.summary = QLabel(summary, self)
        self.summary.setWordWrap(True)
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

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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

    def create_action(self, for_toolbar=True):
        from qt.core import QAction
        action = QAction('Validate with epubveri', self.gui)
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
        summary = 'epubveri %s — %s (%d error(s), %d warning(s))' % (
            envelope.version, verdict,
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

        # A second validation replaces the first window rather than opening
        # another beside it. The dialog is non-modal on purpose — activating a
        # row moves the editor behind it — and without this, validating three
        # times leaves three windows, two of them reporting a book that has
        # since been edited.
        previous = getattr(self, '_results', None)
        if previous is not None:
            previous.close()
        # Kept on the tool so Python does not collect a non-modal dialog.
        self._results = ResultsDialog(self, shown, summary)
        self._results.show()
