# epubveri library check — the library-view action
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""The toolbar button, the background job, and the way back into the library.

**The scan is a `ThreadedJob`, not a modal progress dialog**, and the reason is
arithmetic: a real library is 194 ms a book, so three thousand books is about
ten minutes. calibre's own job mechanism gives that a line in the Jobs panel, a
progress bar, a cancel button and a log, and leaves calibre usable while it
runs. A modal dialog would take the application away for ten minutes and give
nothing back for it.

**`ThreadedJob` calls its callback on the worker thread, and that crashed
calibre.** `start_work` ends `self.callback(self)` inside
`ThreadedJobWorker.run`, so a callback that builds a dialog is building a
QWidget off the GUI thread — undefined behaviour, and in practice the whole
application goes down. Nothing in the class says so; the only hint is a comment
in `_cleanup` that the callback "might be a Dispatch object", and calibre's own
callers (`gui2/email.py`) wrap theirs in `Dispatcher`, which re-emits through a
queued signal onto the thread it was created in. So does this one now.

Two more things about `ThreadedJob` that its docstring gets slightly wrong,
both read off `gui2/threaded_jobs.py` rather than assumed:

  * It says the callback is not called when the user kills a job. `kill()` sets
    the abort event and marks the job killed, but the worker thread is still
    running, and when it returns `start_work` calls the callback as usual —
    `_cleanup` deliberately does not drop it. So a cancelled scan *does* come
    back here, with `job.killed` true, and it comes back **with the books it
    already did**. Ten minutes of work is not thrown away for a change of mind.
  * The worker must check `abort` itself. `scan_books` checks between books,
    which bounds a cancel at one book rather than one library.
"""

from functools import partial

from qt.core import QMenu, QToolButton

from calibre.gui2 import Dispatcher, error_dialog, question_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.threaded_jobs import ThreadedJob

from calibre_plugins.epubveri_library import PLUGIN_NAME, PLUGIN_VERSION
from calibre_plugins.epubveri_library import config as cfg
from calibre_plugins.epubveri_library import install
from calibre_plugins.epubveri_library.results import ResultsDialog
from calibre_plugins.epubveri_library.scan import (ScanReport, collect_jobs,
                                                   scan_books)

#: What the affected books are marked with, so the library search that follows
#: reads `marked:epubveri` rather than the generic `marked:true` — which any
#: other plugin may also be using, and overwriting somebody else's marks with
#: no way to tell whose they were is a rude thing for a plugin to do.
MARK_TEXT = 'epubveri'

#: The search that follows a mark. calibre spells an exact text match this way
#: itself (`mark_books.py`'s `show_marked_text`), and the `=` matters: a bare
#: `marked:epubveri` is a substring match and would also select anything
#: another plugin had marked `epubveri-something`.
MARK_SEARCH = 'marked:"=%s"' % MARK_TEXT

#: One scan at a time. A second would double the process count against the
#: same disk for no gain, and the two reports would arrive over each other.
JOB_TYPE = 'epubveri_library_scan'


class EpubveriLibraryAction(InterfaceAction):

    name = PLUGIN_NAME
    action_spec = ('epubveri', None,
                   'Validate this library with epubveri', None)
    popup_type = QToolButton.ToolButtonPopupMode.MenuButtonPopup
    action_type = 'current'

    def genesis(self):
        self.menu = QMenu(self.gui)
        self.menu.addAction('Check the whole library',
                            partial(self.start, 'library'))
        self.menu.addAction('Check the selected books',
                            partial(self.start, 'selection'))
        self.qaction.setMenu(self.menu)
        # The button itself repeats whichever scope was used last, so the
        # common case is one click and the menu is there for the other one.
        self.qaction.triggered.connect(self.repeat_last)
        icon = self.load_resources(['plugin.png']).get('plugin.png')
        if icon:
            from qt.core import QIcon, QPixmap
            pixmap = QPixmap()
            pixmap.loadFromData(icon)
            self.qaction.setIcon(QIcon(pixmap))

    def _scan_running(self):
        """Is one of ours already going?

        `JobManager` has no per-type count — `unfinished_jobs()` is the whole
        public surface for this — so the type is matched here. Checked rather
        than assumed: an earlier version of this file called a
        `get_group_count` that does not exist in calibre 9.14.
        """
        try:
            jobs = self.gui.job_manager.unfinished_jobs()
        except Exception:                               # noqa: BLE001
            return False
        return any(getattr(job, 'type', None) == JOB_TYPE for job in jobs)

    def repeat_last(self):
        self.start(str(cfg.prefs.get('scope') or 'library'))

    # -- starting ------------------------------------------------------------

    def _book_ids(self, scope):
        if scope == 'selection':
            rows = self.gui.library_view.selectionModel().selectedRows()
            if not rows:
                error_dialog(self.gui, 'epubveri',
                             'Select some books first, or use the menu to '
                             'check the whole library.', show=True)
                return None
            return list(map(self.gui.library_view.model().id, rows))
        db = self.gui.current_db
        return list(db.all_ids())

    def start(self, scope='library'):
        if self._scan_running():
            return error_dialog(
                self.gui, 'epubveri',
                'A library check is already running. Wait for it to finish, '
                'or cancel it in the Jobs panel.', show=True)

        cfg.prefs['scope'] = scope
        book_ids = self._book_ids(scope)
        if book_ids is None:
            return

        report = ScanReport()
        db = self.gui.current_db
        jobs = collect_jobs(db, book_ids, report)
        if not jobs:
            return error_dialog(
                self.gui, 'epubveri',
                'None of those books has an EPUB to check.', show=True)

        if len(jobs) > 500 and not question_dialog(
                self.gui, 'epubveri',
                'Check %d books? On a typical machine that takes about %d '
                'minutes. It runs in the background and you can carry on '
                'using calibre; the Jobs panel can cancel it, and cancelling '
                'still shows what it found.'
                % (len(jobs), max(1, round(len(jobs) * 0.2 / 60.0)))):
            return

        try:
            binary, note = install.ensure_binary(
                autoupdate=cfg.as_bool(cfg.prefs.get('autoupdate')))
        except Exception as exc:                        # noqa: BLE001
            return error_dialog(self.gui, 'epubveri',
                                install.install_failure(exc), show=True)
        if binary is None:
            return error_dialog(self.gui, 'epubveri', note, show=True)
        report.note = note

        job = ThreadedJob(
            JOB_TYPE,
            'epubveri: checking %d book%s' % (len(jobs),
                                              '' if len(jobs) == 1 else 's'),
            func=_run_scan, args=(binary, jobs, report), kwargs={},
            callback=self.dispatched_finish(), killable=True)
        self.gui.job_manager.run_threaded_job(job)
        self.gui.status_bar.show_message(
            'epubveri is checking %d books…' % len(jobs), 5000)

    # -- finishing -----------------------------------------------------------

    def dispatched_finish(self):
        """`finished`, marshalled onto the GUI thread.

        **Not `self.finished`.** `ThreadedJob` calls its callback from the
        worker thread, so passing the bound method directly builds this
        plugin's results dialog off the GUI thread — which took calibre down
        with it on the first real run, a 105-book scan. `Dispatcher` re-emits
        through a queued signal onto the thread it was constructed in, and this
        is constructed while `start` is running, which is the GUI thread.

        The dispatcher is returned rather than stored because `ThreadedJob`
        holds it: `_cleanup` drops `func`, `args` and `kwargs` and deliberately
        keeps `callback` for exactly this reason.
        """
        return Dispatcher(self.finished)

    def finished(self, job):
        report = job.result if job.result is not None else None
        if report is None:
            # Only reachable when the worker raised before returning, which
            # `scan_books` is written not to do — every per-book failure is
            # recorded in the report instead. So this is a real bug, and it
            # goes to the user with the job log behind it rather than being
            # swallowed.
            return self.gui.job_exception(
                job, dialog_title='epubveri could not finish')

        if not report.groups and not report.unreadable:
            from calibre.gui2 import info_dialog
            return info_dialog(
                self.gui, 'epubveri',
                'epubveri found nothing to report in %d book%s.'
                % (report.scanned, '' if report.scanned == 1 else 's'),
                show=True)

        dialog = ResultsDialog(self.gui, report, self.show_books)
        dialog.exec()

    def show_books(self, book_ids, label):
        """Mark the books a row names and filter the library view to them.

        calibre's own idiom, and the reason the report can stay this short:
        the list of affected books does not have to be *displayed* anywhere,
        because the library view is a better list than any table in a dialog —
        it sorts, it shows covers and authors, and double-clicking a row opens
        the book in Edit Book, where the editor plugin says what is wrong with
        it in place.
        """
        # `db.data.set_marked_ids`, not `db.set_marked_ids`: the marks live
        # on the view object, and the database wrapper has no such method in
        # calibre 9.14. Read off calibre's own `mark_books.py` rather than
        # copied from a plugin — the widely-copied `current_db.set_marked_ids`
        # form raises AttributeError here.
        db = self.gui.current_db
        db.data.set_marked_ids(dict.fromkeys(book_ids, MARK_TEXT))
        self.gui.search.set_search_string(MARK_SEARCH)
        self.gui.status_bar.show_message(
            '%d book%s for %s' % (len(book_ids),
                                  '' if len(book_ids) == 1 else 's', label),
            5000)

    def library_changed(self, db):
        # Marks belong to the library they were made in; leaving them behind
        # would make `marked:epubveri` mean nothing in the new one.
        pass


def _run_scan(binary, jobs, report, abort=None, log=None, notifications=None):
    """The worker. Runs in calibre's job thread, so it touches no Qt object.

    `notifications` is the queue `ThreadedJob` reads for the progress bar; it
    takes `(fraction, message)`. Everything else it needs is already decided —
    the binary was resolved on the GUI side precisely so that a ten-minute scan
    cannot replace the validator underneath itself half way through.
    """

    def notify(fraction, title):
        if notifications is not None:
            notifications.put((fraction, title))

    if log is not None:
        log('epubveri %s, %d books' % (PLUGIN_VERSION, len(jobs)))

    scan_books(binary, jobs, report=report, abort=abort, notify=notify)

    if log is not None:
        log('%d scanned, %d rules, %d unreadable, %.1f s'
            % (report.scanned, len(report.groups), len(report.unreadable),
               report.elapsed))
    return report
