"""The details panel: what the selected device or cable is made of.

Like the canvas it decides nothing. It lists what ``viewmodel`` returns and turns a button
into a call to ``operations`` through the document.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from homelab_maker.catalog import CATALOG
from homelab_maker.document import Document
from homelab_maker.gui.canvas import Canvas
from homelab_maker.operations import add_interface, disconnect
from homelab_maker.viewmodel import link_summary, port_rows

_PORT, _CABLE = range(2)


class Inspector(QWidget):
    def __init__(self, document: Document, canvas: Canvas, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inspector")
        self.document = document
        self.canvas = canvas

        self.title = QLabel()
        self.title.setObjectName("inspector-title")
        font = self.title.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + 1)
        self.title.setFont(font)
        self.subtitle = QLabel()
        self.subtitle.setWordWrap(True)

        self.ports = QTableWidget(0, 2)
        self.ports.setObjectName("ports")
        self.ports.setHorizontalHeaderLabels(["Port", "Cable to"])
        self.ports.verticalHeader().setVisible(False)
        self.ports.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.ports.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.ports.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ports.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.add_port_button = QPushButton("Add port")
        self.add_port_button.clicked.connect(self.add_port)
        self.disconnect_button = QPushButton("Remove cable")
        self.disconnect_button.clicked.connect(self.remove_selected_cable)
        self.ports.itemSelectionChanged.connect(self._update_buttons)

        self.cable_text = QLabel()
        self.cable_text.setWordWrap(True)
        self.remove_cable_button = QPushButton("Remove this cable")
        self.remove_cable_button.clicked.connect(self.canvas.delete_selected)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_port_button)
        buttons.addWidget(self.disconnect_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.ports, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.cable_text)
        layout.addWidget(self.remove_cable_button)
        layout.addStretch(0)

        self.document.subscribe(self.refresh)
        self.canvas.selection_changed.connect(self.refresh)
        self.refresh()

    # ----------------------------------------------------------------------- showing

    def shown_node(self) -> str | None:
        ids = self.canvas.selected_ids()
        return ids[0] if len(ids) == 1 else None

    def refresh(self) -> None:
        project = self.document.project
        node_id = self.shown_node()
        node = project.node(node_id) if node_id else None
        link_id = self.canvas.selected_link

        node_widgets = (self.ports, self.add_port_button, self.disconnect_button)
        for widget in node_widgets:
            widget.setVisible(node is not None)
        self.cable_text.setVisible(link_id is not None and node is None)
        self.remove_cable_button.setVisible(link_id is not None and node is None)

        if node is not None:
            kind = CATALOG.get(node.kind)
            self.title.setText(node.name)
            host = project.node(node.parent) if node.parent else None
            where = f"inside {host.name}" if host else "on the canvas"
            self.subtitle.setText(f"{kind.label if kind else node.kind}, {where}")
            self._fill_ports(node.id)
        elif link_id is not None:
            self.title.setText("Cable")
            self.subtitle.setText("")
            self.cable_text.setText(link_summary(project, link_id))
        else:
            count = len(self.canvas.selected_ids())
            self.title.setText("Nothing selected" if count == 0 else f"{count} devices selected")
            self.subtitle.setText(
                "Select a device or a cable to see its details." if count == 0 else ""
            )
        self._update_buttons()

    def _fill_ports(self, node_id: str) -> None:
        rows = port_rows(self.document.project, node_id)
        self.ports.setRowCount(len(rows))
        for index, row in enumerate(rows):
            port = QTableWidgetItem(row.name)
            port.setData(Qt.ItemDataRole.UserRole, row.links)
            cable = QTableWidgetItem(row.peers or "—")
            for item in (port, cable):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.ports.setItem(index, _PORT, port)
            self.ports.setItem(index, _CABLE, cable)

    def _update_buttons(self) -> None:
        links = self._links_of_selected_port()
        self.disconnect_button.setEnabled(bool(links))

    def _links_of_selected_port(self) -> tuple[str, ...]:
        row = self.ports.currentRow()
        item = self.ports.item(row, _PORT) if row >= 0 else None
        if item is None:
            return ()
        value = item.data(Qt.ItemDataRole.UserRole)
        return tuple(value) if value else ()

    # ----------------------------------------------------------------------- editing

    def add_port(self) -> None:
        node_id = self.shown_node()
        if node_id is None:
            return
        try:
            project, _ = add_interface(self.document.project, node_id)
        except ValueError as exc:
            self.canvas.status_message.emit(str(exc))
            return
        self.document.apply(project, "Add port")

    def remove_selected_cable(self) -> None:
        links = self._links_of_selected_port()
        if not links:
            return
        self.document.apply(disconnect(self.document.project, links), "Remove cable")
