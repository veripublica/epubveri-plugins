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
from qt.core import QCheckBox, QGroupBox, QLabel, QVBoxLayout, QWidget

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

#: The scope the dialog opens on, remembered from last time. `library` or
#: `selection`.
prefs.defaults['scope'] = 'library'

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


class ConfigWidget(QWidget):
    """Preferences / Plugins / Customize."""

    def __init__(self):
        QWidget.__init__(self)
        layout = QVBoxLayout(self)

        report = QGroupBox(_('What the report ranks'), self)
        report_layout = QVBoxLayout(report)
        intro = QLabel(
            _('Errors and fatals are always ranked. The rest are fetched '
              'either way — these boxes decide what the table sorts, not '
              'what epubveri looked for, so changing one re-sorts a scan '
              'instead of repeating it.'), report)
        intro.setWordWrap(True)
        report_layout.addWidget(intro)

        self.show_warning = QCheckBox(_('Rank warnings'), report)
        self.show_warning.setChecked(as_bool(prefs.get('show_warning')))
        report_layout.addWidget(self.show_warning)

        self.show_usage = QCheckBox(
            _('Rank usage notes (a feature the book uses, not a defect)'),
            report)
        self.show_usage.setChecked(as_bool(prefs.get('show_usage'), False))
        report_layout.addWidget(self.show_usage)

        self.show_advisory = QCheckBox(
            _('Rank advisory findings (epubveri only; epubcheck is silent '
              'about these and they never change a verdict)'), report)
        self.show_advisory.setChecked(as_bool(prefs.get('show_advisory'), False))
        report_layout.addWidget(self.show_advisory)
        layout.addWidget(report)

        updates = QGroupBox(_('The epubveri validator'), self)
        updates_layout = QVBoxLayout(updates)
        self.autoupdate = QCheckBox(
            _('Check for a newer epubveri (at most once an hour, and never '
              'during a scan)'), updates)
        self.autoupdate.setChecked(as_bool(prefs.get('autoupdate')))
        updates_layout.addWidget(self.autoupdate)
        where = QLabel(
            _('The validator is downloaded on first use and verified against '
              'the release checksums. It is shared with the epubveri editor '
              'plugin, so installing either one is enough.'), updates)
        where.setWordWrap(True)
        updates_layout.addWidget(where)
        layout.addWidget(updates)

        layout.addStretch(1)

    def save_settings(self):
        prefs['show_warning'] = self.show_warning.isChecked()
        prefs['show_usage'] = self.show_usage.isChecked()
        prefs['show_advisory'] = self.show_advisory.isChecked()
        prefs['autoupdate'] = self.autoupdate.isChecked()
