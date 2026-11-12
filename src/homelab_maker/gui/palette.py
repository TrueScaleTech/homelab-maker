"""The list of device kinds to place, built from the catalogue."""

from collections.abc import Sequence

from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget

from homelab_maker.catalog import CATALOG
from homelab_maker.gui.icons import kind_icon
from homelab_maker.gui.theme import Tokens

# What a drag from the list carries: the key of a catalogue kind, as text.
MIME_KIND = "application/x-homelab-maker-kind"


class Palette(QListWidget):
    """Double-click (or press Enter on) a kind to place it, or drag it onto the canvas."""

    kind_chosen = Signal(str)

    def __init__(self, tokens: Tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("palette")
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setIconSize(QSize(26, 26))
        self.setSpacing(2)
        self.setUniformItemSizes(True)
        for kind in CATALOG.values():
            item = QListWidgetItem(kind.label)
            item.setData(Qt.ItemDataRole.UserRole, kind.key)
            self.addItem(item)
        self.itemActivated.connect(self._activated)
        self.set_tokens(tokens)

    def set_tokens(self, tokens: Tokens) -> None:
        colour = QColor(tokens.text)
        for row in range(self.count()):
            item = self.item(row)
            item.setIcon(kind_icon(str(item.data(Qt.ItemDataRole.UserRole)), colour, 26))

    def mimeTypes(self) -> list[str]:
        return [MIME_KIND]

    def mimeData(self, items: Sequence[QListWidgetItem]) -> QMimeData:
        data = QMimeData()
        if items:
            key = str(items[0].data(Qt.ItemDataRole.UserRole))
            data.setData(MIME_KIND, QByteArray(key.encode("utf-8")))
        return data

    def _activated(self, item: QListWidgetItem) -> None:
        self.kind_chosen.emit(str(item.data(Qt.ItemDataRole.UserRole)))
