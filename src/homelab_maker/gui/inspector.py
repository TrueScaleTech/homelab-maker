"""The details panel: what the selected device or cable is made of, and where to change it.

Like the canvas it decides nothing. It lists what ``viewmodel`` returns, turns what is typed
into values with ``fields``, and hands the change to ``operations`` through the document. A
value that is refused is explained in the status bar and the cell goes back to what it was.
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from homelab_maker.fields import (
    format_addresses,
    format_vlans,
    parse_addresses,
    parse_vlan,
    parse_vlans,
)
from homelab_maker.gui.canvas import Canvas
from homelab_maker.model import InterfaceMode, Project
from homelab_maker.operations import (
    add_interface,
    disconnect,
    remove_interface,
    rename_interface,
    set_addresses,
    set_mode,
    set_trunk_vlans,
    set_vlan,
)
from homelab_maker.viewmodel import link_summary, port_rows

PORT, ADDRESSES, MODE, VLAN, TAGGED, CABLE = range(6)
_HEADERS = ["Port", "Addresses", "Mode", "VLAN", "Tagged VLANs", "Cable to"]


class Inspector(QWidget):
    def __init__(self, document: Document, canvas: Canvas, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inspector")
        self.document = document
        self.canvas = canvas
        # True while the table is being filled, so that filling it is not mistaken for typing.
        self._filling = False

        self.title = QLabel()
        self.title.setObjectName("inspector-title")
        font = self.title.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + 1)
        self.title.setFont(font)
        self.subtitle = QLabel()
        self.subtitle.setWordWrap(True)

        self.ports = QTableWidget(0, len(_HEADERS))
        self.ports.setObjectName("ports")
        self.ports.setHorizontalHeaderLabels(_HEADERS)
        self.ports.verticalHeader().setVisible(False)
        self.ports.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.ports.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.ports.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.ports.horizontalHeader().setStretchLastSection(True)
        self.ports.itemChanged.connect(self._item_changed)
        self.ports.itemSelectionChanged.connect(self._update_buttons)

        self.add_port_button = QPushButton("Add port")
        self.add_port_button.clicked.connect(self.add_port)
        self.remove_port_button = QPushButton("Remove port")
        self.remove_port_button.clicked.connect(self.remove_selected_port)
        self.disconnect_button = QPushButton("Remove cable")
        self.disconnect_button.clicked.connect(self.remove_selected_cable)

        self.cable_text = QLabel()
        self.cable_text.setWordWrap(True)
        self.remove_cable_button = QPushButton("Remove this cable")
        self.remove_cable_button.clicked.connect(self.canvas.delete_selected)

        buttons = QHBoxLayout()
        for button in (self.add_port_button, self.remove_port_button, self.disconnect_button):
            buttons.addWidget(button)
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

        for widget in (
            self.ports,
            self.add_port_button,
            self.remove_port_button,
            self.disconnect_button,
        ):
            widget.setVisible(node is not None)
        self.cable_text.setVisible(link_id is not None and node is None)
        self.remove_cable_button.setVisible(link_id is not None and node is None)

        if node is not None:
            kind = CATALOG.get(node.kind)
            self.title.setText(node.name)
            host = project.node(node.parent) if node.parent else None
            where = f"inside {host.name}" if host else "on the canvas"
            self.subtitle.setText(f"{kind.label if kind else node.kind}, {where}")
            self._fill_ports(project, node.id)
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

    def _fill_ports(self, project: Project, node_id: str) -> None:
        keep = self.ports.currentRow()
        self._filling = True
        try:
            rows = port_rows(project, node_id)
            self.ports.setRowCount(len(rows))
            for index, row in enumerate(rows):
                trunk = row.mode == InterfaceMode.TRUNK.value
                cells = {
                    PORT: row.name,
                    ADDRESSES: format_addresses(row.addresses),
                    VLAN: "" if row.vlan is None else str(row.vlan),
                    TAGGED: format_vlans(row.tagged),
                    CABLE: row.peers or "—",
                }
                for column, text in cells.items():
                    item = QTableWidgetItem(text)
                    editable = column in (PORT, ADDRESSES, VLAN) or (column == TAGGED and trunk)
                    flags = item.flags()
                    item.setFlags(
                        flags | Qt.ItemFlag.ItemIsEditable
                        if editable
                        else flags & ~Qt.ItemFlag.ItemIsEditable
                    )
                    if column == PORT:
                        item.setData(Qt.ItemDataRole.UserRole, row.links)
                    self.ports.setItem(index, column, item)
                self.ports.setCellWidget(index, MODE, self._mode_box(row.name, row.mode))
            if 0 <= keep < len(rows):
                self.ports.selectRow(keep)
        finally:
            self._filling = False

    def _mode_box(self, port: str, mode: str) -> QComboBox:
        box = QComboBox()
        box.setObjectName(f"mode-{port}")
        for choice in InterfaceMode:
            box.addItem(choice.value)
        box.setCurrentText(mode)
        box.currentTextChanged.connect(lambda text, name=port: self._mode_chosen(name, text))
        return box

    def _update_buttons(self) -> None:
        has_port = self._selected_port() is not None
        self.disconnect_button.setEnabled(bool(self._links_of_selected_port()))
        self.remove_port_button.setEnabled(has_port)

    def _selected_port(self) -> str | None:
        row = self.ports.currentRow()
        item = self.ports.item(row, PORT) if row >= 0 else None
        return item.text() if item is not None else None

    def _links_of_selected_port(self) -> tuple[str, ...]:
        row = self.ports.currentRow()
        item = self.ports.item(row, PORT) if row >= 0 else None
        if item is None:
            return ()
        value = item.data(Qt.ItemDataRole.UserRole)
        return tuple(value) if value else ()

    # ----------------------------------------------------------------------- editing

    def _edit(self, label: str, change: Callable[[Project], Project]) -> None:
        """Apply a change as one undoable step, or explain why not and show the old value."""
        try:
            project = change(self.document.project)
        except ValueError as exc:
            self.canvas.status_message.emit(str(exc))
            self.refresh()
            return
        if project == self.document.project:
            self.refresh()
            return
        self.document.apply(project, label)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        node_id = self.shown_node()
        port_item = self.ports.item(item.row(), PORT)
        if self._filling or node_id is None or port_item is None:
            return
        # The row's port, as the document knows it: the cell may be the port name itself.
        names = [row.name for row in port_rows(self.document.project, node_id)]
        port = names[item.row()] if item.row() < len(names) else port_item.text()
        text = item.text()
        column = item.column()
        if column == PORT:
            self._edit("Rename port", lambda p: rename_interface(p, node_id, port, text))
        elif column == ADDRESSES:
            self._edit(
                "Change addresses",
                lambda p: set_addresses(p, node_id, port, parse_addresses(text)),
            )
        elif column == VLAN:
            self._edit("Change VLAN", lambda p: set_vlan(p, node_id, port, parse_vlan(text)))
        elif column == TAGGED:
            self._edit(
                "Change tagged VLANs",
                lambda p: set_trunk_vlans(p, node_id, port, parse_vlans(text)),
            )

    def _mode_chosen(self, port: str, text: str) -> None:
        node_id = self.shown_node()
        if self._filling or node_id is None:
            return
        self._edit("Change port mode", lambda p: set_mode(p, node_id, port, InterfaceMode(text)))

    def add_port(self) -> None:
        node_id = self.shown_node()
        if node_id is None:
            return
        self._edit("Add port", lambda p: add_interface(p, node_id)[0])

    def remove_selected_port(self) -> None:
        node_id, port = self.shown_node(), self._selected_port()
        if node_id is None or port is None:
            return
        self._edit("Remove port", lambda p: remove_interface(p, node_id, port))

    def remove_selected_cable(self) -> None:
        links = self._links_of_selected_port()
        if not links:
            return
        self.document.apply(disconnect(self.document.project, links), "Remove cable")
