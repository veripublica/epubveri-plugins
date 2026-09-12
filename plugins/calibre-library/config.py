# epubveri library — preferences
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Settings, and the one place this plugin's defaults differ from the editor's.

**The editor plugin shows usage and advisory findings by default; this one does
not, and the reason is that they answer different questions.** The editor panel
shows one book completely, so hiding part of its report would be hiding
something from the person looking at that book. This table *ranks a library's
defects*, and a usage finding is not a defect — it names a feature the book
uses. Ranked in, `CSS-028` (an `@font-face` declaration) tops the list on any
real library and teaches nothing; the row is true and useless, which is exactly
the failure the advisory family is tuned away from.

Both are still fetched — the runner always passes `-u --advisory` — so the
filter is a display choice, and the dialog says how many findings it is
leaving out rather than pretending they do not exist. Turning either on
re-sorts the table; it never re-validates the library.
"""

from calibre.utils.config import JSONConfig
from qt.core import (QCheckBox, QHBoxLayout, QLabel, QPushButton, QSpinBox,
                     QVBoxLayout, QWidget)

#: Its own file. The binary and the record of which binary it is are shared
#: with the editor plugin (see `install.py`); the settings are not, because
#: they are answers to different questions and a user may reasonably want the
#: editor loud and this table quiet.
prefs = JSONConfig('plugins/epubveri_library')

#: Spelled as the editor plugin spells it, so the two never disagree about
#: what the setting is called even though each keeps its own answer.
prefs.defaults['autoupdate'] = True

prefs.defaults['show_warning'] = True
prefs.defaults['show_usage'] = False
prefs.defaults['show_advisory'] = False

#: **There was a `scope` setting here and it is gone.** It remembered whether
#: the last scan was the whole library or a selection, so that a plain click on
#: the toolbar button could repeat it. The button no longer starts a scan — it
#: opens the menu, because nothing on it could say which of the two was about
#: to run — so the value was written on every scan and read by nobody.

#: How many books are validated at once. **0 means "work it out", and that is
#: the default rather than a number.**
#:
#: A fixed default is wrong in both directions and there is no value that is
#: not: four is timid on a publisher's workstation with 128 GB and too many on
#: a four-core laptop with 8 GB. So the default computes itself from the
#: machine *and* the library — see `scan.recommended_workers` — and the
#: setting exists because we still cannot know whether this library sits on an
#: NVMe or a network share, which decides whether more workers help at all.
prefs.defaults['workers'] = 0

_ON_VALUES = frozenset(['yes', 'true', 'on', '1', 'y'])


def as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _ON_VALUES


def severities():
    """The severities the report ranks, worst first.

    `fatal` and `error` are not optional: they are what decides a verdict, and
    a report that can be configured to hide them is not a validator's report.
    """
    out = ['fatal', 'error']
    if as_bool(prefs.get('show_warning')):
        out.append('warning')
    if as_bool(prefs.get('show_usage'), False):
        out.append('usage')
        out.append('info')
    return tuple(out)


def show_advisory():
    return as_bool(prefs.get('show_advisory'), False)


def workers(jobs=()):
    """The worker count for a scan: the user's, or one computed for them.

    Clamped to the cap on read rather than only on write, because the settings
    file is editable by hand and a number typed there should not be able to
    ask for sixty processes.
    """
    from calibre_plugins.epubveri_library.scan import (recommended_workers,
                                                       worker_cap)
    try:
        chosen = int(prefs.get('workers') or 0)
    except (TypeError, ValueError):
        chosen = 0
    if chosen <= 0:
        return recommended_workers(jobs)
    return max(1, min(chosen, worker_cap()))


class ConfigWidget(QWidget):
    """Preferences / Plugins / Customize.

    **Four short sections in one column, and there is a scar here.** The page
    had grown a section per release and was taller than the dialog that opens
    it, so it was rebuilt as a `QTabWidget` — which fixed the height (432 px of
    stacked sections became 208) and brought a worse bug: clicking one
    particular tab dropped calibre's modal Customize dialog behind the
    Preferences window, where only Escape got out. Never reproduced here,
    across the real dialog with real mouse events, with and without a parent
    window; reproduced every time on the owner's machine, and photographed.

    The dialog, its modality and its placement are calibre's. The only lever
    this file has is what it puts inside, so the tab widget is gone and the
    height is solved the way it should have been first: **the page is short
    because its text is short.** Each control is one line, and the paragraph
    explaining it is its tooltip — which is where an explanation you need once
    belongs, rather than permanently occupying the page.

    Do not reintroduce tabs to make room. If a fifth section ever needs one,
    that is the signal that the section belongs somewhere else.
    """

    #: How narrow a wrapped caption may get. calibre puts this page inside a
    #: `QScrollArea`, where a label that demands width buys a horizontal
    #: scrollbar rather than a wider window — this page asked for 704 px
    #: against a 682 px viewport once.
    NOTE_WIDTH = 320

    def __init__(self):
        QWidget.__init__(self)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        self._section(
            layout, _('What the report ranks'),
            _('Errors and fatals always. These re-sort, never re-scan.'))
        self.show_warning = self._check(
            _('Warnings'),
            _('Errors and fatals are always ranked. Everything is fetched '
              'either way, so changing this re-sorts a scan instead of '
              'repeating it.'))
        self.show_warning.setChecked(as_bool(prefs.get('show_warning')))
        layout.addWidget(self.show_warning)
        self.show_usage = self._check(
            _('Usage notes'),
            _('A feature the book uses rather than a defect — an @font-face '
              'declaration, an epub:type outside the default vocabulary. '
              'Ranked in, they top the list on any real library and teach '
              'nothing.'))
        self.show_usage.setChecked(as_bool(prefs.get('show_usage'), False))
        layout.addWidget(self.show_usage)
        self.show_advisory = self._check(
            _('Advisory findings'),
            _("epubveri's own: epubcheck is silent about these and they never "
              'change a verdict.'))
        self.show_advisory.setChecked(as_bool(prefs.get('show_advisory'), False))
        layout.addWidget(self.show_advisory)

        layout.addSpacing(10)
        self._section(
            layout, _('Scanning'),
            _('Two cores are kept for the rest of the system.'))
        from calibre_plugins.epubveri_library.scan import (recommended_workers,
                                                          worker_cap)
        cap = worker_cap()
        row = QHBoxLayout()
        label = QLabel(_('Books validated at the same time:'), self)
        row.addWidget(label)
        self.workers = QSpinBox(self)
        self.workers.setRange(0, cap)
        # 0 is not "none" here; it is "decide for me", which is the default and
        # wants to read as a choice rather than as an empty box.
        # **Short, because a spin box sizes itself to its longest text.**
        # "Automatic (8 here, now)" read better and was three words wider than
        # the box calibre's scroll area has room for, so it arrived clipped to
        # "utomatic (8 here, now)". The sentence it was compressing is in the
        # tooltip with the rest.
        automatic = _('Automatic (%d)') % recommended_workers()
        self.workers.setSpecialValueText(automatic)
        # **A spin box sizes itself to its number range, not to its special
        # value text**, so this one arrived clipped to "utomatic (8)" — the
        # box was wide enough for "8". Measured off the widget's own font
        # rather than padded by a guess, because the text is translated and a
        # guess that fits English is a clipped box in German.
        self.workers.setMinimumWidth(
            self.workers.fontMetrics().horizontalAdvance(automatic)
            + self.workers.fontMetrics().height() * 2)
        try:
            self.workers.setValue(min(cap, max(0, int(prefs.get('workers') or 0))))
        except (TypeError, ValueError):
            self.workers.setValue(0)
        row.addWidget(self.workers)
        row.addStretch(1)
        layout.addLayout(row)
        explain = _('Automatic is %(auto)d on this machine right now. The '
                    'maximum is %(cap)d: two cores are kept for the rest of '
                    'the system, including calibre itself. More is not always '
                    'faster, and not every core is worth the same — a machine '
                    'that mixes fast and efficient cores gains less than its '
                    'core count suggests. If a scan is not getting quicker, '
                    'or the machine becomes uncomfortable to use while one '
                    'runs, this is the number to lower.')  % {
                        'auto': recommended_workers(), 'cap': cap}
        for widget in (label, self.workers):
            widget.setToolTip(explain)

        layout.addSpacing(10)
        self._section(
            layout, _('The validator'),
            _('Downloaded on first use, checked against the release '
              'checksums. Its companion is the "epubveri" Edit book tool.'))
        self.autoupdate = self._check(
            _('Check for a newer epubveri'),
            _('At most once an hour, and never during a scan. The validator '
              'is downloaded on first use and verified against the release '
              'checksums. This plugin keeps its own copy, so a library scan '
              'is never interrupted by the editor plugin updating one '
              'underneath it.'))
        self.autoupdate.setChecked(as_bool(prefs.get('autoupdate')))
        layout.addWidget(self.autoupdate)

        layout.addSpacing(10)
        self._section(
            layout, _('Saved reports'),
            _('The last two whole-library scans. They hold book titles.'))
        saved_row = QHBoxLayout()
        self.saved_note = QLabel(self)
        self.saved_note.setToolTip(
            _('The last two whole-library scans are kept, so a report '
              'survives calibre restarting and the two can be compared. They '
              'include the titles of the books each defect was found in.'))
        saved_row.addWidget(self.saved_note)
        saved_row.addStretch(1)
        self.forget = QPushButton(_('Delete saved reports'), self)
        self.forget.setToolTip(self.saved_note.toolTip())
        self.forget.clicked.connect(self._forget)
        saved_row.addWidget(self.forget)
        layout.addLayout(saved_row)
        self._show_saved_size()

        layout.addStretch(1)

    # -- the small pieces ----------------------------------------------------

    def _heading(self, text, note):
        """A section title and the one line underneath it.

        **Bold text, not a `QGroupBox`.** A group box costs a frame, a margin
        and a title row per section — most of the height that made this page
        too tall, for decoration four bold words provide.

        The note is the middle term between the two versions this page has
        had. Paragraphs made it too tall; nothing but labels made it *"çok
        sade"* — a column of bare words with no hint what ranking a usage note
        would do to you. One dimmed line a section costs about 14 px and says
        the thing a first-time reader needs; the full argument is still a
        tooltip away on the control it belongs to.
        """
        heading = QLabel('<b>%s</b>' % text, self)
        caption = QLabel(note, self)
        caption.setWordWrap(True)
        caption.setMinimumWidth(self.NOTE_WIDTH)
        font = caption.font()
        font.setPointSizeF(max(9.0, font.pointSizeF() - 2.0))
        caption.setFont(font)
        caption.setStyleSheet('color: palette(mid);')
        return heading, caption

    def _section(self, layout, text, note):
        heading, caption = self._heading(text, note)
        layout.addWidget(heading)
        layout.addWidget(caption)

    def _check(self, text, explanation):
        """A one-line checkbox whose paragraph lives in its tooltip.

        **A `QCheckBox` does not wrap**, so its label is an unbreakable demand
        on the dialog's width — and calibre puts this page inside a
        `QScrollArea`, so a long one buys a horizontal scrollbar rather than a
        wider window. Short label, long tooltip.
        """
        box = QCheckBox(text, self)
        box.setToolTip(explanation)
        return box

    # -- the saved reports ---------------------------------------------------

    def _show_saved_size(self):
        from calibre_plugins.epubveri_library import store
        files, total = store.stored_size()
        if not files:
            self.saved_note.setText(_('Nothing saved yet.'))
        else:
            # **KB below a megabyte, because that is where these actually
            # live.** A 474-book library compresses to about 20 KB; printed as
            # megabytes that is `0.0 MB`, which reads as *nothing is stored*
            # directly above a button offering to delete it.
            size = (_('%.0f KB') % (total / 1024.0) if total < 1024 * 1024
                    else _('%.1f MB') % (total / (1024.0 * 1024.0)))
            self.saved_note.setText(
                _('%(files)d file%(s)s, %(size)s')
                % {'files': files, 's': '' if files == 1 else 's',
                   'size': size})
        self.forget.setEnabled(bool(files))

    def _forget(self):
        """**Not behind a confirmation.** What it deletes is a cache of work
        that can be produced again by running a scan, and the button says
        exactly what it does; a dialog asking "are you sure" about a thing
        that costs nothing to undo teaches people to click through dialogs."""
        from calibre_plugins.epubveri_library import store
        store.forget_all()
        self._show_saved_size()

    def save_settings(self):
        prefs['show_warning'] = self.show_warning.isChecked()
        prefs['show_usage'] = self.show_usage.isChecked()
        prefs['show_advisory'] = self.show_advisory.isChecked()
        prefs['autoupdate'] = self.autoupdate.isChecked()
        prefs['workers'] = self.workers.value()
