# epubveri for calibre — the Edit Book tool
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
#
# ---------------------------------------------------------------------------
# STATUS: skeleton. The parts below that touch epubveri are real and are the
# same ones the Sigil plugin is tested on; the parts that touch calibre are
# written from its published plugin API and have NOT yet been run inside
# calibre. Do not ship this without doing that.
#
# What is still missing, so that nobody has to guess: a results view (calibre
# plugins usually dock a QTreeWidget rather than open a dialog), jumping the
# editor to a finding's file and line, a preferences page for the two display
# switches, and the update check.
# ---------------------------------------------------------------------------

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.tweak_book.plugin import Tool
from calibre.utils.config import JSONConfig
from qt.core import QCheckBox, QLabel, QVBoxLayout, QWidget

from client import binary as bin_mod
from client import runner
from client.envelope import EnvelopeError


#: calibre's own store, so the settings live where a calibre user expects them
#: and survive a plugin upgrade.
prefs = JSONConfig('plugins/epubveri')
prefs.defaults['update'] = 'yes'


class ConfigWidget(QWidget):
    """Preferences / Plugins / Customize.

    One checkbox, and it is about **the network rather than the version**.
    Someone who clears it is saying "do not use my connection" — a metered
    link, an air-gapped machine, or preference — not "keep me on an older
    validator", which nobody wants from a tool whose releases are mostly fixes
    for wrong errors.

    So clearing it stops every network call, and says nothing further about
    it. What it does not stop is the line telling you how old the binary is
    after a long time without a check: that is an explanation for a finding
    that looks wrong, not a nag to update.
    """

    def __init__(self):
        QWidget.__init__(self)
        layout = QVBoxLayout(self)
        self.check_updates = QCheckBox(
            'Keep epubveri up to date automatically', self)
        self.check_updates.setChecked(
            str(prefs['update']).strip().lower() in ('yes', 'true', 'on', '1', 'y'))
        self.check_updates.setToolTip(
            'Reads 842 bytes of checksums at most once an hour and installs a '
            'newer epubveri if there is one, verifying it first.\n'
            'Clear this to make the plugin use the network never.')
        layout.addWidget(self.check_updates)
        note = QLabel(
            'epubveri itself is downloaded once, on first use, and verified '
            'against the release checksums.\nWith this off it is never '
            'updated, and the report says how old it is after a month.', self)
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

    def save_settings(self):
        # The same key and the same vocabulary as the Sigil plugin, so the
        # two never disagree about what the setting is called.
        prefs['update'] = 'yes' if self.check_updates.isChecked() else 'no'


class EpubVeriTool(Tool):
    """One entry in the editor's Plugins menu and toolbar."""

    name = 'epubveri'
    allowed_in_toolbar = True
    allowed_in_menu = True

    def create_action(self, for_toolbar=True):
        from qt.core import QAction
        action = QAction(self.name, self.gui)
        action.triggered.connect(self.validate)
        return action

    # -- the epubveri half, shared in shape with the Sigil plugin -----------

    def _plugin_dir(self):
        return os.path.dirname(os.path.abspath(__file__))

    def _binary(self):
        path = os.path.join(self._plugin_dir(), bin_mod.binary_filename())
        if os.path.isfile(path):
            return path
        # First use: fetch the release build for this platform and verify it
        # against that release's SHA256SUMS.txt before it is ever executed.
        return bin_mod.download_binary(self._plugin_dir())

    def validate(self):
        # calibre keeps the book open and unsaved edits in memory, so the file
        # on disk is not necessarily what the user is looking at. The container
        # has to be written out before epubveri sees it — this is the piece
        # that must be checked against calibre's own API before shipping.
        container = self.current_container
        if container is None:
            return error_dialog(self.gui, 'epubveri', 'No book is open.',
                                show=True)
        epub_path = container.path_to_ebook

        try:
            envelope = runner.run_epubveri(self._binary(), epub_path)
        except (EnvelopeError, bin_mod.DownloadError, OSError) as exc:
            return error_dialog(self.gui, 'epubveri', str(exc), show=True)

        if envelope.could_not_read:
            return error_dialog(self.gui, 'epubveri',
                                envelope.error or 'The book could not be read.',
                                show=True)

        verdict = 'VALID' if envelope.is_valid else 'NOT VALID'
        info_dialog(
            self.gui, 'epubveri',
            'epubveri %s — %s\n%d error(s), %d warning(s)' % (
                envelope.version, verdict,
                envelope.count('error') + envelope.count('fatal'),
                envelope.count('warning')),
            show=True)
