"""The checks panel: what looks wrong or fragile in the drawing, one line each.

Double-click a line (or press Enter on it) to go to the first device it talks about.
"""

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from homelab_maker.checks import Finding, Severity, run_checks
from homelab_maker.document import Document
from homelab_maker.gui.theme import Tokens


class FindingsPanel(QWidget):
    # The number of warnings, for the status bar.
    counted = Signal(int)

    def __init__(self, document: Document, tokens: Tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("findings")
        self.document = document
        self.tokens = tokens
        self.findings: list[Finding] = []

        self.summary = QLabel()
        self.list = QListWidget()
        self.list.setObjectName("findings-list")
        self.list.setWordWrap(True)
        self.list.setAlternatingRowColors(False)
        self.list.itemActivated.connect(self._activated)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.summary)
        layout.addWidget(self.list, 1)

        # Set by the main window: how to show a device that may be inside another one.
        self.reveal: Callable[[str], None] = lambda node_id: None
        document.subscribe(self.refresh)
        self.refresh()

    def set_tokens(self, tokens: Tokens) -> None:
        self.tokens = tokens
        self._colour_items()

    def refresh(self) -> None:
        self.findings = run_checks(self.document.project)
        self.list.clear()
        for finding in self.findings:
            label = "Warning" if finding.severity is Severity.WARNING else "Note"
            item = QListWidgetItem(f"{label}: {finding.message}")
            item.setToolTip(finding.check.value)
            self.list.addItem(item)
        self._colour_items()
        warnings = sum(1 for f in self.findings if f.severity is Severity.WARNING)
        notes = len(self.findings) - warnings
        if not self.findings:
            self.summary.setText("Nothing to report.")
        else:
            self.summary.setText(f"{_count(warnings, 'warning')}, {_count(notes, 'note')}")
        self.counted.emit(warnings)

    def _colour_items(self) -> None:
        for row, finding in enumerate(self.findings):
            warning = finding.severity is Severity.WARNING
            colour = self.tokens.warning if warning else self.tokens.text_muted
            self.list.item(row).setForeground(QBrush(QColor(colour)))

    def _activated(self, item: QListWidgetItem) -> None:
        row = self.list.row(item)
        if 0 <= row < len(self.findings) and self.findings[row].nodes:
            self.reveal(self.findings[row].nodes[0])


def _count(number: int, word: str) -> str:
    return f"{number} {word}{'' if number == 1 else 's'}"
