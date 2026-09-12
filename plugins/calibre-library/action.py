# epubveri library — the library-view action
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
from calibre_plugins.epubveri_library import store
from calibre_plugins.epubveri_library.compare import Comparison
from calibre_plugins.epubveri_library.results import CompareDialog, ResultsDialog
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
    #: `(text, icon, tooltip, shortcut)`. The icon is set in `genesis` from the
    #: zip instead — `action_spec`'s slot names one of calibre's own icons, not
    #: a plugin resource. The shortcut is an **empty tuple, not None**: None
    #: registers no shortcut at all, so the action never appears under
    #: Preferences / Advanced / Shortcuts and a user cannot bind one; an empty tuple
    #: registers it with no default binding, which is what we want — a
    #: ten-minute scan does not deserve a key combination of our choosing, but
    #: someone who runs it daily should be able to pick one.
    #: **A verb phrase, not the brand.** calibre's toolbar row is all verbs —
    #: Add books, Edit metadata, Convert books, Remove books, Tweak ePub — and
    #: a bare "epubveri" sat wrong among them *and* read as the same thing as
    #: the editor plugin, whose button says "Validate with epubveri". Same
    #: verb, different object; the brand is carried by the icon and by the
    #: tooltip, which is where a user goes when the label is not enough.
    action_spec = ('Validate library', None,
                   'Validate this library with epubveri', ())

    #: **Where calibre may offer to put this, and three of these are
    #: correctness rather than taste.** On installing a plugin calibre shows
    #: `ChoosePluginToolbarsDialog` listing every location this does not
    #: forbid, so an entry here is the only way to keep the action out of a
    #: place it does not belong.
    #:
    #: The device locations are excluded because `_book_ids('selection')`
    #: reads `gui.library_view.selectionModel()`, which still holds the
    #: **library's** selection while a device view is showing. Invoked from a
    #: device context menu the action would quietly check books the user
    #: cannot see. Reaching for `current_view()` instead would not help: books
    #: on a device are not in the library database and there is nothing here
    #: to scan.
    #:
    #: The search bar is excluded because it is a row of search controls, not
    #: a place for a ten-minute job.
    dont_add_to = frozenset([
        'toolbar-device', 'menubar-device', 'context-menu-device',
        'searchbar',
    ])
    #: **Neither half of this button starts a scan, and it keeps its arrow.**
    #:
    #: A plain click used to repeat whichever scope was used last — one click
    #: cheaper, and invisible: nothing on the button says whether it is about
    #: to check three selected books or three thousand, and being wrong about
    #: that costs ten minutes. (The README has said the button does not scan
    #: since 0.1.0, and the line that would have made it true was never
    #: committed, so the promise and the behaviour disagreed for five days.)
    #:
    #: `InstantPopup` was the obvious fix and cost something real: it drops
    #: the drop-down arrow, and every other menu-bearing button in calibre has
    #: one, so ours stopped looking like part of the application (owner,
    #: 2026-09-12). `MenuButtonPopup` keeps the arrow — and the body of the
    #: button, which it would otherwise wire to the action, is connected to
    #: opening the same menu. Both halves do one thing, the arrow says there
    #: is a menu, and nothing here can start ten minutes of work by accident.
    popup_type = QToolButton.ToolButtonPopupMode.MenuButtonPopup
    action_type = 'current'

    def genesis(self):
        #: The window a scan last put up, or None. Held because a modeless
        #: dialog with no reference is collected out from under the user.
        self._dialog = None
        #: The report itself, which outlives its window. Set here and not only
        #: in `finished`: the menu reads it, and a menu can be opened before
        #: anything has ever been scanned.
        self.last_report = None

        self.menu = QMenu(self.gui)
        self.menu.addAction('Check the whole library',
                            partial(self.start, 'library'))
        self.menu.addAction('Check the selected books',
                            partial(self.start, 'selection'))
        self.menu.addSeparator()
        # **These three were written with the methods below and never reached
        # a menu**, which is how maddz came to report that closing the window
        # loses the scan (MobileRead 375207 #14): the answer existed and there
        # was no way to ask for it. `create_menu_action` rather than
        # `addAction` so each is offered under Preferences / Advanced /
        # Shortcuts with no default binding — someone who scans daily can bind
        # one, and we pick nothing on their behalf.
        self.again_action = self.create_menu_action(
            self.menu, 'epubveri_library_last', 'Show the last report',
            shortcut=None, triggered=self.show_last_report)
        self.no_epub_action = self.create_menu_action(
            self.menu, 'epubveri_library_no_epub', 'Show books with no EPUB',
            shortcut=None, triggered=self.show_books_without_epub)
        self.compare_action = self.create_menu_action(
            self.menu, 'epubveri_library_compare',
            'Compare with the previous scan',
            shortcut=None, triggered=self.compare_with_previous)
        self.clear_action = self.create_menu_action(
            self.menu, 'epubveri_library_clear', 'Clear the marks it left',
            shortcut=None, triggered=self.clear_marks)
        # Greyed out rather than hidden when there is nothing to show: a menu
        # whose items appear and disappear teaches nobody what the plugin can
        # do, and a disabled entry says the report is gone, which is true.
        self.menu.aboutToShow.connect(self._sync_menu)
        self._sync_menu()

        self.qaction.setMenu(self.menu)
        # The arrow half opens the menu because Qt does that for
        # `MenuButtonPopup`; this is the other half.
        self.qaction.triggered.connect(self.show_menu)
        icon = self.load_resources(['plugin.png']).get('plugin.png')
        if icon:
            from qt.core import QIcon, QPixmap
            pixmap = QPixmap()
            pixmap.loadFromData(icon)
            self.qaction.setIcon(QIcon(pixmap))

    def _library_id(self):
        try:
            return self.gui.current_db.library_id
        except Exception:                               # noqa: BLE001
            return None

    def show_menu(self):
        """Open the menu from a click on the button itself.

        **Asked of the widget rather than popped at the cursor**, so the menu
        appears under the button the way the arrow's does — two ways of
        opening one menu that dropped it in two different places would be
        worse than the missing arrow this replaces.

        The action can be in several bars at once, and a user may have put it
        in none of them; `associatedObjects` is the list Qt keeps for exactly
        this, and the cursor is the fallback for when nothing in it is a
        toolbar we can find a button in.
        """
        from qt.core import QCursor, QToolBar, QToolButton
        try:
            for owner in self.qaction.associatedObjects():
                if not isinstance(owner, QToolBar):
                    continue
                button = owner.widgetForAction(self.qaction)
                if isinstance(button, QToolButton) and button.isVisible():
                    return button.showMenu()
        except Exception:                               # noqa: BLE001
            pass
        self.menu.exec(QCursor.pos())

    def _sync_menu(self):
        """What the report items can do right now.

        **Asks the filesystem whether a file exists, never what is in it.**
        This runs every time the menu opens, and a stored report is megabytes;
        loading one to decide whether to grey out an entry would put a disk
        read in front of every click.
        """
        report = getattr(self, 'last_report', None)
        library_id = self._library_id()
        has_saved = report is not None or store.exists(library_id)
        self.again_action.setEnabled(has_saved)
        self.no_epub_action.setEnabled(bool(report and report.no_format))
        self.compare_action.setEnabled(
            has_saved and store.exists(library_id, store.PREVIOUS))
        self.clear_action.setEnabled(bool(self._marked_ids()))

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

        book_ids = self._book_ids(scope)
        if book_ids is None:
            return

        report = ScanReport()
        report.scope = scope
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

        # Kept even when there is nothing to report: a clean library can still
        # hold books with no EPUB, and that menu item reads this.
        self.last_report = report
        # **Saved even when it found nothing, and that is the interesting
        # case.** A library that came back clean is exactly the baseline a
        # later comparison wants, and a scan is only cheap to repeat until it
        # is ten minutes long. `save` returns whether it wrote and never
        # raises: a full disk costs the stored copy, never the report about to
        # open in front of the user.
        #
        # **A selection is not saved**, because saving it would demote a
        # whole-library baseline and put a five-book scan opposite a
        # three-thousand-book one — where every rule the five books do not
        # happen to contain reads as a rule that was repaired. The report is
        # still shown, and still in `last_report` for this session; it is only
        # not made the thing a later comparison measures against.
        if report.scope == 'library':
            store.save(self._library_id(), report)
        if not report.groups and not report.unreadable:
            from calibre.gui2 import info_dialog
            return info_dialog(
                self.gui, 'epubveri',
                'epubveri found nothing to report in %d book%s.'
                % (report.scanned, '' if report.scanned == 1 else 's'),
                show=True)

        self._open_report(report)

    def _open_report(self, report):
        """Put the report up, **modeless**.

        `exec()` is what this used to do, and a modal window cannot be the
        thing it is here: its whole purpose is to hand books to the library
        view behind it, which nobody can look at while a modal dialog is up.
        That is why the dialog closed itself on every row click, and why an
        eight-minute scan could be lost to one (maddz, MobileRead 375207 #14).

        Modeless costs two things and both are handled here. The reference has
        to be kept, or Python collects a window the user is looking at. And a
        second scan must not leave two reports on screen claiming to describe
        the same library, so the previous one is closed first — `finished`
        clears the slot before `WA_DeleteOnClose` deletes the widget, so
        nothing here ever touches a deleted object.
        """
        from qt.core import Qt
        self._close_report()
        dialog = ResultsDialog(self.gui, report, self.show_books)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._report_closed)
        self._dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _report_closed(self, _result=0):
        self._dialog = None

    def _close_report(self):
        dialog, self._dialog = getattr(self, '_dialog', None), None
        if dialog is not None:
            dialog.close()

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

    def show_last_report(self):
        """The report again, without re-reading a single book.

        A ten-minute scan whose window closes is a ten-minute scan lost, and
        the closing is one stray click. This is the whole of the answer: the
        report object is still in memory, and rebuilding the dialog over it
        costs nothing. It does not survive calibre restarting, which the menu
        item does not pretend otherwise about — it simply is not there when
        there is nothing to show.
        """
        if self.last_report is None:
            # Loaded here rather than at startup. A stored report is megabytes
            # and most calibre sessions never ask for one, so reading it on
            # the click is the difference between a plugin that costs nothing
            # to have installed and one that costs a disk read every launch.
            self.last_report = store.load(self._library_id())
        if self.last_report is None:
            return error_dialog(
                self.gui, 'epubveri',
                'There is no saved report for this library. Run a check and '
                'this will bring its report back afterwards, including after '
                'calibre has been restarted.', show=True)
        self._open_report(self.last_report)

    def compare_with_previous(self):
        """This library's last two scans, subtracted.

        **The question no single report can answer**: not *what is wrong with
        my library* but *is it better than it was*. That is the one this
        family of tools is shaped around — epubveri finds, epubsana repairs —
        and the answer lives in the difference rather than in either scan.
        """
        # **Both sides come off disk, including the one that may be in
        # memory.** Reaching for `last_report` would put whatever was scanned
        # most recently on the right-hand side — a selection, most likely,
        # since that is the scan people run between full ones. The stored
        # slots are whole-library scans by construction, so they are
        # comparable by construction.
        library_id = self._library_id()
        after = store.load(library_id)
        before = store.load(library_id, store.PREVIOUS)
        if after is None or before is None:
            return error_dialog(
                self.gui, 'epubveri',
                'There are not two saved scans of this library yet. The '
                'comparison needs the last one and the one before it; check '
                'the library again and it will have both.', show=True)
        self._close_report()
        dialog = CompareDialog(self.gui, Comparison(before, after),
                               self.show_books)
        from qt.core import Qt
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._report_closed)
        self._dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def show_books_without_epub(self):
        """The books a scan could not look at.

        The summary line counts them, which is honest but not actionable —
        "12 without an EPUB" leaves the user to find out which twelve. They are
        the books most likely to want attention, since a missing format is
        usually a conversion that never happened.
        """
        report = self.last_report
        if not report or not report.no_format:
            return
        self.show_books({r.book_id for r in report.no_format}, 'no EPUB')

    def _marked_ids(self):
        """The books *we* marked, by the text we mark with.

        `clear_marks` has called this since it was written and it was never
        defined — which nothing noticed, because the menu entry that reaches
        it was never connected either. Both halves of that are fixed together.

        `marked_ids` is an attribute of the view object rather than of its
        class, so it does not show up on `calibre.db.view.View`; it is read
        off a live one. Anything here can be absent — there may be no library
        open when the menu is first built — so a failure is "nothing of ours"
        rather than an exception thrown into calibre's menu code.
        """
        try:
            marked = self.gui.current_db.data.marked_ids
        except Exception:                               # noqa: BLE001
            return set()
        return {book_id for book_id, text in marked.items()
                if text == MARK_TEXT}

    def clear_marks(self):
        """Remove only our own marks.

        `set_marked_ids` replaces the whole map, so clearing by handing it an
        empty one would throw away marks another plugin or the user had made.
        Ours are the ones whose text is `MARK_TEXT`.
        """
        db = self.gui.current_db
        ours = self._marked_ids()
        if not ours:
            return
        remaining = {book_id: text for book_id, text
                     in db.data.marked_ids.items() if book_id not in ours}
        db.data.set_marked_ids(remaining)
        if str(self.gui.search.text()).startswith('marked:'):
            self.gui.search.set_search_string('')
        self.gui.status_bar.show_message(
            'cleared %d epubveri mark%s'
            % (len(ours), '' if len(ours) == 1 else 's'), 5000)

    def library_changed(self, db):
        """A report is about the library it was made in.

        Its rows carry book ids, and an id means a different book in another
        library — so *Show affected books* on a stale report would mark
        whatever happened to share those numbers. Dropping it is the only
        honest thing to do, and it is why this hook is implemented rather than
        left as the base class's no-op.

        **The window goes with it**, which the modal version got for free:
        nobody could change libraries while a modal dialog was up. A modeless
        one left open over a library it does not describe is the same wrong
        mark, one click further away.
        """
        self.last_report = None
        self._close_report()
        # The new library has its own two slots on disk, so nothing is lost by
        # dropping this one — `show_last_report` will read the right file.
        self._sync_menu()


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

    def write(message):
        if log is not None:
            log(message)

    # **What the first line has to carry is whatever cannot be recovered
    # afterwards.** A scan that dies leaves only this: which plugin, which
    # binary, and how long one book was allowed to take — the three things a
    # reader would otherwise have to guess at from a half-finished log.
    write('epubveri library %s, %d books' % (PLUGIN_VERSION, len(jobs)))
    write('validator: %s' % binary)

    # The user's setting, or a value worked out from this machine and this
    # library. Resolved here rather than inside `scan_books` so the scan
    # function stays a function of its arguments and the tests can drive it
    # without a preferences file.
    parallel = cfg.workers(jobs)
    scan_books(binary, jobs, report=report, abort=abort, notify=notify,
               log=write, workers=parallel)

    # The rate is here because it is the question people actually ask. DNSB
    # scanned 18 000 books and reasonably wondered whether an hour and a half
    # was normal (MobileRead 375207 #2); with this line the run answers that
    # itself instead of being compared against someone else's machine.
    rate = report.elapsed / report.scanned if report.scanned else 0.0
    write('%d scanned, %d rules, %d unreadable, %.1f s, %.3f s/book'
          % (report.scanned, len(report.groups), len(report.unreadable),
             report.elapsed, rate))
    return report
