# epubveri for calibre — the editor tool
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

from client import binary as bin_mod
from client import runner
from client.envelope import EnvelopeError


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
