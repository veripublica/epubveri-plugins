# epubveri library — what changed between two scans
# Copyright (C) 2026 Baris Kayadelen
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of this repository.
"""Two dated observations, subtracted.

The report this plugin produces answers *what is wrong with my library*. Two of
them answer a question no validator asks and the veripublica tools are shaped
around: **epubveri finds, epubsana repairs, and did that help?** A row going
from 181 books to 12 is the answer, and it is not derivable from either scan
alone.

**The confound is named rather than avoided.** Two scans of one library can
differ because the books changed or because epubveri did — a release adds a
rule, splits a message id, or stops reporting something. Nothing here can tell
those apart, so `Comparison.same_validator` says whether the question is even
well posed, and the window says so out loud when it is not. The alternative,
refusing to compare across versions, would be worse: most of the interesting
comparisons a user makes will span a release, because our releases are more
frequent than their scans.
"""


class Change:
    """One rule, before and after.

    Either side may be zero: a rule with `before` 0 is one the second scan
    started reporting, and `after` 0 is one it stopped.
    """

    __slots__ = ('key', 'group', 'before_books', 'after_books',
                 'before_findings', 'after_findings')

    def __init__(self, key, group, before, after):
        self.key = key
        #: A `RuleGroup` from whichever side has one — the newer by
        #: preference, since its message wording is the current one. Held so
        #: the window can show a code, a severity and an example without
        #: re-deriving any of them here.
        self.group = group
        self.before_books = before.books if before is not None else 0
        self.after_books = after.books if after is not None else 0
        self.before_findings = before.findings if before is not None else 0
        self.after_findings = after.findings if after is not None else 0

    @property
    def books_delta(self):
        """**Books, and there is deliberately no findings equivalent.**

        A findings count moves for reasons the user did not cause — one
        repaired paragraph can take a thousand findings with it, and one added
        book can add as many — so a `findings_delta` would be a number that
        looks like progress and is mostly noise. The two findings counts are
        shown side by side instead, which says the same thing without ranking
        anything by it.
        """
        return self.after_books - self.before_books

    @property
    def state(self):
        if self.before_books == 0:
            return 'new'
        if self.after_books == 0:
            return 'gone'
        if self.books_delta < 0:
            return 'better'
        if self.books_delta > 0:
            return 'worse'
        return 'same'

    @property
    def sort_key(self):
        """**Biggest movement first, in either direction, and unchanged rows
        last.**

        Not "most books", which is the report's own ordering and the wrong one
        here: a row on 400 books that did not move is the least interesting
        line in a comparison, and a row that went from 181 to 0 is the most.
        Ties break on the size of the row and then on the code, so the order is
        total and two runs cannot disagree about it.
        """
        return (0 if self.books_delta else 1, -abs(self.books_delta),
                -max(self.after_books, self.before_books),
                self.group.code if self.group else '')


class Comparison:
    """Everything two scans say about each other."""

    def __init__(self, before, after):
        self.before = before
        self.after = after
        self.changes = []
        keys = set(before.groups) | set(after.groups)
        for key in keys:
            old = before.groups.get(key)
            new = after.groups.get(key)
            self.changes.append(Change(key, new or old, old, new))
        self.changes.sort(key=lambda change: change.sort_key)

    @property
    def same_validator(self):
        """Were both scans run by the same epubveri?

        Unknown counts as **not** the same: an older stored report may carry no
        version at all, and silence is not agreement.
        """
        return bool(self.before.tool_version) and \
            self.before.tool_version == self.after.tool_version

    def rows(self, severities, advisory=True):
        """The changes a filter admits, by the severity of the row as it
        stands now — the same reading the report window uses, so a user who
        turns warnings off sees the same set of rules in both places."""
        wanted = set(severities)
        out = []
        for change in self.changes:
            group = change.group
            if group is None or group.severity not in wanted:
                continue
            if not advisory and group.is_advisory:
                continue
            out.append(change)
        return out

    def moved(self, rows=None):
        """`(better, worse)` counted in rules, not findings.

        Rules because that is what this table's lines are, and because a
        findings count moves for reasons a user did not cause — one repaired
        paragraph can take a thousand findings with it.
        """
        rows = self.changes if rows is None else rows
        better = sum(1 for change in rows if change.books_delta < 0)
        worse = sum(1 for change in rows if change.books_delta > 0)
        return better, worse

    def books_touched(self, rows=None):
        """Every book named by either side of a row that moved.

        The useful thing to hand the library view from here: *show me the books
        this comparison is about*.
        """
        rows = self.changes if rows is None else rows
        ids = set()
        for change in rows:
            if not change.books_delta:
                continue
            for report in (self.before, self.after):
                group = report.groups.get(change.key)
                if group is not None:
                    ids |= group.book_ids
        return ids
