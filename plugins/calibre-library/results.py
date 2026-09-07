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
is something a row *hands you* rather than the subject, and the way out of the
window is into calibre's own library view with those books selected.
"""

import csv
import io
import os

from qt.core import (QAbstractItemView, QApplication, QCheckBox, QDialog,
                     QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                     QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, Qt)

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
        self.export = QPushButton('Export…', self)
        self.export.clicked.connect(self._export)
        buttons.addButton(self.export, QDialogButtonBox.ButtonRole.ActionRole)
        self.copy = QPushButton('Copy', self)
        self.copy.clicked.connect(self._copy)
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
        if not ids:
            return info_dialog(self, 'epubveri',
                               'No books to show for %s.' % label, show=True)
        self.on_show_books(set(ids), label)
        self.accept()

    def _as_rows(self):
        yield ('message', 'rule', 'violation_kind', 'name', 'severity',
               'books', 'findings', 'example')
        for group in self._rows():
            yield (group.code, group.rule or '', group.violation_kind or '',
                   group.name or '', group.severity, group.books,
                   group.findings, group.label)

    def _as_csv(self):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for row in self._as_rows():
            writer.writerow(row)
        return buffer.getvalue()

    def _copy(self):
        QApplication.clipboard().setText(self._as_csv())
        self.copy.setText('Copied')

    def _export(self):
        path, _filter = QFileDialog.getSaveFileName(
            self, 'Export the report', os.path.expanduser(
                '~/epubveri-library-report.csv'), 'CSV (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8', newline='') as handle:
                handle.write(self._as_csv())
        except OSError as exc:
            return error_dialog(self, 'epubveri',
                                'The report could not be written.',
                                det_msg=str(exc), show=True)
        info_dialog(self, 'epubveri', 'Report written to\n%s' % path,
                    show=True)


def plugin_version():
    return PLUGIN_VERSION
