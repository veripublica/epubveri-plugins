# epubveri library — the report window
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""One row per defect, ordered by how many books carry it.

The table is the argument in `scan.py` made visible: a library's report is a
short list of recurring producer defects, not a long list of books. Everything
here follows from that — the default ordering is by book count, the book list
is something a row *hands you* rather than the subject, and a row hands it to
calibre's own library view rather than to a second table in here.

**The window is modeless, and that is load-bearing rather than a style.** It
was modal at first, which forced it to close as soon as it filtered the
library — there is no point marking books behind a window the user cannot
leave. The cost was that one click on a row spent the whole scan: maddz has a
library that takes eight minutes (MobileRead 375207 #14). Modeless, a row is a
question the report can be asked over and over, and the caller keeps the
window rather than the dialog keeping the caller.
"""

import csv
import io
import os

from qt.core import (QAbstractItemView, QApplication, QCheckBox, QDialog,
                     QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                     QMenu, QPushButton, QTreeWidget, QTreeWidgetItem,
                     QVBoxLayout, Qt)

from calibre.gui2 import error_dialog, info_dialog

from calibre_plugins.epubveri_library import PLUGIN_VERSION
from calibre_plugins.epubveri_library import config as cfg

#: Column order. `BOOKS` before `FINDINGS` because the first is the ranking and
#: the second is the detail — a row on 181 books matters whether it fires once
#: per book or forty times.
COL_CODE, COL_WHAT, COL_SEVERITY, COL_BOOKS, COL_FINDINGS = range(5)

_HEADERS = ('Message', 'What it says', 'Severity', 'Books', 'Findings')


class RuleItem(QTreeWidgetItem):
    """A row that sorts on its numbers rather than on their spelling.

    Qt compares the display text unless `__lt__` says otherwise, and the
    display text of 1 000 sorts before 99. The comparison reads the group
    directly, so what the column *shows* and what it *sorts by* cannot drift
    apart.
    """

    def __init__(self, parent, group):
        QTreeWidgetItem.__init__(self, parent)
        self.group = group
        self.setText(COL_CODE, group.code)
        self.setText(COL_WHAT, group.label)
        self.setToolTip(COL_WHAT, group.example)
        self.setText(COL_SEVERITY,
                     'ADVISORY' if group.is_advisory else group.severity.upper())
        self.setText(COL_BOOKS, str(group.books))
        self.setText(COL_FINDINGS, str(group.findings))
        self.setTextAlignment(COL_BOOKS, Qt.AlignmentFlag.AlignRight |
                              Qt.AlignmentFlag.AlignVCenter)
        self.setTextAlignment(COL_FINDINGS, Qt.AlignmentFlag.AlignRight |
                              Qt.AlignmentFlag.AlignVCenter)
        if group.rule:
            self.setToolTip(COL_CODE, '%s\n%s' % (group.code, group.rule))

    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        if column == COL_BOOKS:
            return self.group.books < other.group.books
        if column == COL_FINDINGS:
            return self.group.findings < other.group.findings
        if column == COL_SEVERITY:
            return self.group.sort_key[2] < other.group.sort_key[2]
        return self.text(column).lower() < other.text(column).lower()


class ResultsDialog(QDialog):
    """The report. `on_show_books(ids)` is what the library view does with a
    row; it is passed in rather than reached for, so this file never touches
    calibre's GUI state and can be opened in a test."""

    def __init__(self, gui, report, on_show_books):
        QDialog.__init__(self, gui)
        self.gui = gui
        self.report = report
        self.on_show_books = on_show_books
        self.setWindowTitle('epubveri library')
        self.resize(900, 560)

        layout = QVBoxLayout(self)
        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        # **A second line, for the conditions rather than the findings.** The
        # summary above is about the library; this is about the run — when,
        # with which epubveri, on what machine, how fast. Smaller and quieter
        # because it is reference rather than reading, and separate because
        # the two go stale at different speeds: the findings describe books
        # that may since have been repaired, the conditions never change.
        self.conditions = QLabel(self)
        self.conditions.setWordWrap(True)
        self.conditions.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        font = self.conditions.font()
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1.0))
        self.conditions.setFont(font)
        layout.addWidget(self.conditions)

        self.table = QTreeWidget(self)
        self.table.setHeaderLabels(list(_HEADERS))
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemDoubleClicked.connect(self._double_clicked)
        layout.addWidget(self.table, 1)

        toggles = QHBoxLayout()
        self.warnings = QCheckBox('Warnings', self)
        self.warnings.setChecked(cfg.as_bool(cfg.prefs.get('show_warning')))
        self.usage = QCheckBox('Usage notes', self)
        self.usage.setChecked(cfg.as_bool(cfg.prefs.get('show_usage'), False))
        self.advisory = QCheckBox('Advisory', self)
        self.advisory.setChecked(cfg.show_advisory())
        for box in (self.warnings, self.usage, self.advisory):
            box.stateChanged.connect(self._refilter)
            toggles.addWidget(box)
        toggles.addStretch(1)
        self.hidden = QLabel(self)
        toggles.addWidget(self.hidden)
        layout.addLayout(toggles)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.show_books = QPushButton('Show affected books', self)
        self.show_books.clicked.connect(self._show_books)
        buttons.addButton(self.show_books,
                          QDialogButtonBox.ButtonRole.ActionRole)
        # **Two exports, because the table answers one question and DNSB
        # asked the other** (MobileRead 375207 #13). The report is about
        # rules; a row says 181 books carry a defect and the library view is
        # where you go to see which. That is the right default and it is not
        # a file you can hand to somebody, sort in a spreadsheet, or keep
        # beside next month's. The book-level CSV is that file, and it is a
        # second menu entry rather than a second button because it is the
        # rarer of the two.
        self.export = QPushButton('Export…', self)
        self.export_menu = QMenu(self)
        self.export_menu.addAction('Report — one row per defect…',
                                   self._export)
        self.export_menu.addAction('Books — one row per book and defect…',
                                   self._export_books)
        self.export.setMenu(self.export_menu)
        buttons.addButton(self.export, QDialogButtonBox.ButtonRole.ActionRole)
        # **Copy offers the run as well as the table**, because the two get
        # pasted into different places. The CSV goes into a spreadsheet; the
        # conditions go into a forum post, where "1 000 books in 48 s" means
        # nothing without the cores, the worker count and the epubveri version
        # beside it (owner, 2026-09-12). Plain text rather than CSV for that
        # reason — nobody imports a forum post.
        self.copy = QPushButton('Copy', self)
        self.copy_menu = QMenu(self)
        self.copy_menu.addAction('The report, as CSV', self._copy)
        self.copy_menu.addAction('What this scan was', self._copy_conditions)
        self.copy.setMenu(self.copy_menu)
        buttons.addButton(self.copy, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._fill()

    # -- what the checkboxes mean -------------------------------------------

    def _severities(self):
        out = ['fatal', 'error']
        if self.warnings.isChecked():
            out.append('warning')
        if self.usage.isChecked():
            out.extend(('usage', 'info'))
        return tuple(out)

    def _rows(self):
        rows = self.report.rows(self._severities())
        if not self.advisory.isChecked():
            rows = [g for g in rows if not g.is_advisory]
        return rows

    # -- filling -------------------------------------------------------------

    def _fill(self):
        # Sorting off while the rows go in, or Qt re-sorts the whole table once
        # per row. Turned back on afterwards — and note that the sibling
        # plugin's 0.4.2 bug was exactly this call, whose side effect of
        # clearing `sectionsClickable` is not in its name. Nothing here has a
        # hand-written header slot to be silenced, which is why that defect
        # cannot recur in this window.
        self.table.setSortingEnabled(False)
        self.table.clear()
        rows = self._rows()
        for group in rows:
            RuleItem(self.table, group)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(COL_BOOKS, Qt.SortOrder.DescendingOrder)
        for column in range(len(_HEADERS)):
            self.table.resizeColumnToContents(column)
        self.table.setColumnWidth(COL_WHAT,
                                  min(420, self.table.columnWidth(COL_WHAT)))
        self._describe(rows)

    def _visible_ids(self):
        """Every book named by a row the filter is currently showing.

        Not `ScanReport.affected_ids`, which knows about severities and not
        about the advisory toggle. One function reading `_rows()` cannot
        disagree with the table the way two computations of the same set can.
        """
        ids = set()
        for group in self._rows():
            ids |= group.book_ids
        return ids

    def _refilter(self):
        self._fill()

    def _describe(self, rows):
        report = self.report
        parts = []
        if report.cancelled:
            parts.append('Cancelled after %d of %d books'
                         % (report.scanned, report.requested))
        else:
            parts.append('%d book%s scanned in %.0f s'
                         % (report.scanned, '' if report.scanned == 1 else 's',
                            report.elapsed))
        affected = len(self._visible_ids())
        parts.append('%d row%s, %d book%s affected'
                     % (len(rows), '' if len(rows) == 1 else 's',
                        affected, '' if affected == 1 else 's'))
        if report.tool_version:
            parts.append('epubveri %s' % report.tool_version)
        if report.no_format:
            parts.append('%d without an EPUB' % len(report.no_format))
        if report.unreadable:
            parts.append('%d could not be read' % len(report.unreadable))
        line = ' · '.join(parts)
        if report.note:
            line += '\n' + report.note
        self.summary.setText(line)
        self.conditions.setText(
            ' · '.join('%s %s' % (label, value)
                       for label, value in report.conditions()))

        hidden = self.report.hidden_counts(self._severities())
        if not self.advisory.isChecked():
            adv = sum(g.findings for g in self.report.groups.values()
                      if g.is_advisory and g.severity in self._severities())
            if adv:
                hidden['advisory'] = adv
        if hidden:
            self.hidden.setText(
                'hidden: ' + ', '.join('%d %s' % (n, word)
                                       for word, n in sorted(hidden.items())))
        else:
            self.hidden.setText('')

    # -- actions -------------------------------------------------------------

    def _selected_groups(self):
        items = self.table.selectedItems()
        seen, groups = set(), []
        for item in items:
            if id(item.group) not in seen:
                seen.add(id(item.group))
                groups.append(item.group)
        return groups

    def _double_clicked(self, item, _column):
        self._show_ids(item.group.book_ids, item.group.code)

    def _show_books(self):
        groups = self._selected_groups()
        if groups:
            ids = set()
            for group in groups:
                ids |= group.book_ids
            label = groups[0].code if len(groups) == 1 else 'selected rows'
        else:
            # No selection means the whole report, which is the useful
            # default: "show me every book this scan has something to say
            # about" is a question, and it is one click.
            ids = self._visible_ids()
            label = 'all findings'
        self._show_ids(ids, label)

    def _show_ids(self, ids, label):
        """Hand the books to the library view and **stay open**.

        It used to close itself here, and that followed from the window being
        modal: a modal dialog is what the user is doing, so filtering the
        library behind one that could not be left would have shown them
        nothing. maddz reported the consequence rather than the cause
        (MobileRead 375207 #14) — one click on a row and an eight-minute scan
        was gone. The window is modeless now, so a row is a question the
        report can be asked repeatedly.
        """
        if not ids:
            return info_dialog(self, 'epubveri',
                               'No books to show for %s.' % label, show=True)
        self.on_show_books(set(ids), label)

    def _as_rows(self):
        yield ('message', 'rule', 'violation_kind', 'name', 'severity',
               'books', 'findings', 'example')
        for group in self._rows():
            yield (group.code, group.rule or '', group.violation_kind or '',
                   group.name or '', group.severity, group.books,
                   group.findings, group.label)

    def _titles(self):
        """`{book_id: title}` for everything the scan looked at.

        The report keeps titles on `ScanReport.books` because that is where
        the scan put them; the groups keep ids, because an id is what the
        library view wants. This is the one place the two have to meet.
        """
        return {result.book_id: result.title for result in self.report.books}

    def _as_book_rows(self):
        """One row per book and defect, in the order the scan ran.

        **The same filter as the table**, which is the honest reading of
        "export what I am looking at": a checkbox that changes the window and
        not the file would make two artefacts out of one report. The count is
        this book's own, not the row's — a defect on 181 books and a book that
        trips it forty times are different facts, and a set of ids could only
        have carried the first.

        Books the scan could not read are not here. They have no defects to
        list, and the window already counts them.
        """
        yield ('book_id', 'title', 'message', 'rule', 'violation_kind',
               'name', 'severity', 'findings', 'what it says')
        titles = self._titles()
        order = {result.book_id: index
                 for index, result in enumerate(self.report.books)}
        rows = self._rows()
        per_book = {}
        for group in rows:
            for book_id, count in group.book_counts.items():
                per_book.setdefault(book_id, []).append((group, count))
        for book_id in sorted(per_book, key=lambda b: (order.get(b, 1 << 30), b)):
            for group, count in per_book[book_id]:
                yield (book_id, titles.get(book_id, ''), group.code,
                       group.rule or '', group.violation_kind or '',
                       group.name or '', group.severity, count, group.example)

    def _as_csv(self, rows=None):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for row in (self._as_rows() if rows is None else rows):
            writer.writerow(row)
        return buffer.getvalue()

    def _copy(self):
        # With the preamble, like the file. **Everything that leaves this
        # window carries the conditions it was produced under**, and the one
        # exception is the menu entry that is nothing else.
        QApplication.clipboard().setText(
            self._as_csv(self._with_preamble(self._as_rows())))
        self.copy.setText('Copied')

    def _conditions_text(self):
        return '\n'.join('%s: %s' % (label, value)
                          for label, value in self.report.conditions())

    def _copy_conditions(self):
        QApplication.clipboard().setText(self._conditions_text())
        self.copy.setText('Copied')

    def _preamble(self):
        """The conditions, as CSV rows ahead of the table.

        Two columns and then the header, rather than `#` comments: a comment
        convention is a thing each spreadsheet decides for itself, whereas
        every one of them reads a two-cell row. The blank row is what stops
        the preamble and the table being read as one block.
        """
        for label, value in self.report.conditions():
            yield (label, value)
        yield ()

    def _export(self):
        self._write_csv('Export the report', 'epubveri-library-report.csv',
                        self._as_rows())

    def _export_books(self):
        self._write_csv('Export the books', 'epubveri-library-books.csv',
                        self._as_book_rows())

    def _with_preamble(self, rows):
        for row in self._preamble():
            yield row
        for row in rows:
            yield row

    def _write_csv(self, title, filename, rows):
        """Ask for a path and write it. One function, because the only thing
        that differs between the two exports is which rows go in."""
        path, _filter = QFileDialog.getSaveFileName(
            self, title, os.path.join(os.path.expanduser('~'), filename),
            'CSV (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8', newline='') as handle:
                handle.write(self._as_csv(self._with_preamble(rows)))
        except OSError as exc:
            return error_dialog(self, 'epubveri',
                                'The report could not be written.',
                                det_msg=str(exc), show=True)
        info_dialog(self, 'epubveri', 'Written to\n%s' % path, show=True)


#: Column order for the comparison. The two counts sit either side of the
#: change so a row reads left to right as a sentence: 181, 12, -169.
CMP_CODE, CMP_WHAT, CMP_BEFORE, CMP_AFTER, CMP_DELTA, CMP_FINDINGS = range(6)

_CMP_HEADERS = ('Message', 'What it says', 'Books before', 'Books after',
                'Change', 'Findings')


class ChangeItem(QTreeWidgetItem):
    """One rule, before and after. Sorts on its numbers, like `RuleItem`."""

    def __init__(self, parent, change):
        QTreeWidgetItem.__init__(self, parent)
        self.change = change
        group = change.group
        self.setText(CMP_CODE, group.code)
        self.setText(CMP_WHAT, group.label)
        self.setToolTip(CMP_WHAT, group.example)
        self.setText(CMP_BEFORE, str(change.before_books))
        self.setText(CMP_AFTER, str(change.after_books))
        # **A sign on every number that has one.** `-169` and `+3` say which
        # way a row went without the reader comparing two columns, and this is
        # the column people will scan. Zero is written as `=` rather than `0`,
        # because a row that did not move is a different kind of fact from one
        # that moved by nothing.
        delta = change.books_delta
        self.setText(CMP_DELTA, '=' if not delta else '%+d' % delta)
        self.setText(CMP_FINDINGS, '%d → %d' % (change.before_findings,
                                                change.after_findings))
        for column in (CMP_BEFORE, CMP_AFTER, CMP_DELTA):
            self.setTextAlignment(column, Qt.AlignmentFlag.AlignRight |
                                  Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        if column == CMP_BEFORE:
            return self.change.before_books < other.change.before_books
        if column == CMP_AFTER:
            return self.change.after_books < other.change.after_books
        if column == CMP_DELTA:
            # **By how far a row moved, not by which way** — `Change.sort_key`,
            # the same order the CSV comes out in. A plain numeric sort here
            # would put every regression at one end, where a table filtered to
            # moved rows buries the handful of rows a user most wants: the
            # ones that got worse. The direction is not lost by this, it is
            # in the sign on every cell and in the summary's two counts.
            #
            # It is also the reason this is not left to Qt's default. The
            # first version enabled sorting without naming a column, Qt sorted
            # on the message id, and the window and its own export disagreed
            # about the order of the same rows — found by running a real
            # before/after rather than by reading the code.
            return self.change.sort_key < other.change.sort_key
        if column == CMP_FINDINGS:
            return self.change.after_findings < other.change.after_findings
        return self.text(column).lower() < other.text(column).lower()


class CompareDialog(QDialog):
    """Two scans of one library, subtracted.

    Deliberately the same shape as `ResultsDialog` — same filters, same
    ordering discipline, same way out into the library view — because it
    answers the same question one release later. What it adds is the line at
    the top, which says what the two scans were and, when they were run by
    different epubveri versions, that the difference may be ours rather than
    the library's.
    """

    def __init__(self, gui, comparison, on_show_books):
        QDialog.__init__(self, gui)
        self.gui = gui
        self.comparison = comparison
        self.on_show_books = on_show_books
        self.setWindowTitle('epubveri library — what changed')
        self.resize(940, 560)

        layout = QVBoxLayout(self)
        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.caveat = QLabel(self)
        self.caveat.setWordWrap(True)
        layout.addWidget(self.caveat)

        self.table = QTreeWidget(self)
        self.table.setHeaderLabels(list(_CMP_HEADERS))
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemDoubleClicked.connect(self._double_clicked)
        layout.addWidget(self.table, 1)

        toggles = QHBoxLayout()
        self.warnings = QCheckBox('Warnings', self)
        self.warnings.setChecked(cfg.as_bool(cfg.prefs.get('show_warning')))
        self.usage = QCheckBox('Usage notes', self)
        self.usage.setChecked(cfg.as_bool(cfg.prefs.get('show_usage'), False))
        self.advisory = QCheckBox('Advisory', self)
        self.advisory.setChecked(cfg.show_advisory())
        self.unchanged = QCheckBox('Rules that did not move', self)
        self.unchanged.setChecked(False)
        for box in (self.warnings, self.usage, self.advisory, self.unchanged):
            box.stateChanged.connect(self._fill)
            toggles.addWidget(box)
        toggles.addStretch(1)
        layout.addLayout(toggles)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.show_books = QPushButton('Show the books that moved', self)
        self.show_books.clicked.connect(self._show_books)
        buttons.addButton(self.show_books,
                          QDialogButtonBox.ButtonRole.ActionRole)
        self.copy = QPushButton('Copy', self)
        self.copy.clicked.connect(self._copy)
        buttons.addButton(self.copy, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._fill()

    # -- filling -------------------------------------------------------------

    def _severities(self):
        out = ['fatal', 'error']
        if self.warnings.isChecked():
            out.append('warning')
        if self.usage.isChecked():
            out.extend(('usage', 'info'))
        return tuple(out)

    def _rows(self):
        rows = self.comparison.rows(self._severities(),
                                    advisory=self.advisory.isChecked())
        if not self.unchanged.isChecked():
            rows = [change for change in rows if change.books_delta]
        return rows

    def _fill(self):
        self.table.setSortingEnabled(False)
        self.table.clear()
        rows = self._rows()
        for change in rows:
            ChangeItem(self.table, change)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(CMP_DELTA, Qt.SortOrder.AscendingOrder)
        for column in range(len(_CMP_HEADERS)):
            self.table.resizeColumnToContents(column)
        self.table.setColumnWidth(CMP_WHAT,
                                  min(380, self.table.columnWidth(CMP_WHAT)))
        self._describe(rows)

    def _describe(self, rows):
        comparison = self.comparison
        better, worse = comparison.moved(rows)
        parts = ['%d rule%s better, %d worse'
                 % (better, '' if better == 1 else 's', worse)]
        for label, report in (('before', comparison.before),
                              ('after', comparison.after)):
            when = (report.started_at.strftime('%Y-%m-%d %H:%M')
                    if report.started_at is not None else 'an earlier scan')
            parts.append('%s: %s, %d books, epubveri %s'
                         % (label, when, report.scanned,
                            report.tool_version or 'unknown'))
        self.summary.setText(' · '.join(parts))
        if comparison.same_validator:
            self.caveat.setText('')
        else:
            # **Said out loud, because the number above is not what it looks
            # like when this is true.** A rule can appear, vanish or change
            # its count because we changed, and no comparison can tell that
            # apart from a library that changed.
            self.caveat.setText(
                'These two scans were run by different versions of epubveri, '
                'so some of this difference may be ours rather than your '
                "library's — a rule we added, changed or stopped reporting "
                'looks exactly like a book that was repaired.')

    # -- actions -------------------------------------------------------------

    def _double_clicked(self, item, _column):
        ids = set()
        for report in (self.comparison.before, self.comparison.after):
            group = report.groups.get(item.change.key)
            if group is not None:
                ids |= group.book_ids
        self._show_ids(ids, item.change.group.code)

    def _show_books(self):
        items = self.table.selectedItems()
        if items:
            rows = [item.change for item in items]
            label = (items[0].change.group.code if len(items) == 1
                     else 'selected rows')
        else:
            rows, label = self._rows(), 'everything that moved'
        self._show_ids(self.comparison.books_touched(rows), label)

    def _show_ids(self, ids, label):
        if not ids:
            return info_dialog(self, 'epubveri',
                               'No books to show for %s.' % label, show=True)
        self.on_show_books(set(ids), label)

    def _as_rows(self):
        yield ('message', 'rule', 'severity', 'books_before', 'books_after',
               'books_change', 'findings_before', 'findings_after', 'state',
               'what it says')
        for change in self._rows():
            group = change.group
            yield (group.code, group.rule or '', group.severity,
                   change.before_books, change.after_books,
                   change.books_delta, change.before_findings,
                   change.after_findings, change.state, group.example)

    def _preamble(self):
        """Both scans' conditions, each prefixed, then a blank row.

        Prefixed because a comparison file that carried one undated pair of
        columns would be the exact artefact this release exists to stop
        producing.
        """
        for label, report in (('before', self.comparison.before),
                              ('after', self.comparison.after)):
            for key, value in report.conditions():
                yield ('%s %s' % (label, key), value)
        yield ()

    def _copy(self):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for row in self._preamble():
            writer.writerow(row)
        for row in self._as_rows():
            writer.writerow(row)
        QApplication.clipboard().setText(buffer.getvalue())
        self.copy.setText('Copied')


def plugin_version():
    return PLUGIN_VERSION
