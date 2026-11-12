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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from homelab_maker.catalog import CATALOG
from homelab_maker.document import Document
from homelab_maker.fields import (
    format_addresses,
    format_vlans,
    parse_addresses,
    parse_port,
    parse_reference,
    parse_vlan,
    parse_vlans,
)
from homelab_maker.gui.canvas import Canvas
from homelab_maker.model import (
    InterfaceMode,
    Project,
    Protocol,
    Rule,
    RuleAction,
    RuleProtocol,
    Service,
    node_routes,
)
from homelab_maker.operations import (
    add_interface,
    add_rule,
    add_service,
    disconnect,
    move_rule,
    remove_interface,
    remove_rule,
    remove_service,
    rename_interface,
    replace_rule,
    replace_service,
    set_addresses,
    set_mode,
    set_trunk_vlans,
    set_vlan,
)
from homelab_maker.viewmodel import link_summary, port_rows, reference_label

PORT, ADDRESSES, MODE, VLAN, TAGGED, CABLE = range(6)
_HEADERS = ["Port", "Addresses", "Mode", "VLAN", "Tagged VLANs", "Cable to"]
SERVICE_NAME, SERVICE_PORT, SERVICE_PROTOCOL = range(3)
RULE_ACTION, RULE_FROM, RULE_TO, RULE_PROTOCOL, RULE_PORT = range(5)


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
        ports_page = QWidget()
        ports_layout = QVBoxLayout(ports_page)
        ports_layout.setContentsMargins(0, 6, 0, 0)
        ports_layout.addWidget(self.ports, 1)
        ports_layout.addLayout(buttons)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("node-tabs")
        self.tabs.addTab(ports_page, "Ports")
        self.tabs.addTab(self._build_services(), "Services")
        self.tabs.addTab(self._build_rules(), "Rules")

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.cable_text)
        layout.addWidget(self.remove_cable_button)
        layout.addStretch(0)

        self.document.subscribe(self.refresh)
        self.canvas.selection_changed.connect(self.refresh)
        self.refresh()

    def _table(self, headers: list[str], name: str) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setObjectName(name)
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _page(self, table: QTableWidget, *buttons: QPushButton) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.addWidget(table, 1)
        row = QHBoxLayout()
        for button in buttons:
            row.addWidget(button)
        layout.addLayout(row)
        return page

    def _build_services(self) -> QWidget:
        self.services = self._table(["Service", "Port", "Protocol"], "services")
        self.services.itemChanged.connect(self._service_changed)
        self.add_service_button = QPushButton("Add service")
        self.add_service_button.clicked.connect(self.add_service_row)
        self.remove_service_button = QPushButton("Remove service")
        self.remove_service_button.clicked.connect(self.remove_service_row)
        return self._page(self.services, self.add_service_button, self.remove_service_button)

    def _build_rules(self) -> QWidget:
        self.rules = self._table(["Action", "From", "To", "Protocol", "Port"], "rules")
        self.rules.itemChanged.connect(self._rule_changed)
        self.add_rule_button = QPushButton("Add rule")
        self.add_rule_button.clicked.connect(self.add_rule_row)
        self.remove_rule_button = QPushButton("Remove rule")
        self.remove_rule_button.clicked.connect(self.remove_rule_row)
        self.rule_up_button = QPushButton("Move up")
        self.rule_up_button.clicked.connect(lambda: self.move_rule_row(-1))
        self.rule_down_button = QPushButton("Move down")
        self.rule_down_button.clicked.connect(lambda: self.move_rule_row(1))
        note = QLabel(
            "Rules are tried from the top and the first that fits decides. "
            "A flow that no rule mentions is allowed."
        )
        note.setWordWrap(True)
        page = self._page(
            self.rules,
            self.add_rule_button,
            self.remove_rule_button,
            self.rule_up_button,
            self.rule_down_button,
        )
        page.layout().addWidget(note)  # type: ignore[union-attr]
        return page

    # ----------------------------------------------------------------------- showing

    def shown_node(self) -> str | None:
        ids = self.canvas.selected_ids()
        return ids[0] if len(ids) == 1 else None

    def refresh(self) -> None:
        project = self.document.project
        node_id = self.shown_node()
        node = project.node(node_id) if node_id else None
        link_id = self.canvas.selected_link

        self.tabs.setVisible(node is not None)
        self.cable_text.setVisible(link_id is not None and node is None)
        self.remove_cable_button.setVisible(link_id is not None and node is None)

        if node is not None:
            kind = CATALOG.get(node.kind)
            self.title.setText(node.name)
            host = project.node(node.parent) if node.parent else None
            where = f"inside {host.name}" if host else "on the canvas"
            self.subtitle.setText(f"{kind.label if kind else node.kind}, {where}")
            self._fill_ports(project, node.id)
            self._fill_services(node.id)
            self._fill_rules(node.id)
            self.tabs.setTabVisible(2, node_routes(node))
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

    def _fill_services(self, node_id: str) -> None:
        node = self.document.project.node(node_id)
        services = node.services if node else ()
        self._filling = True
        try:
            self.services.setRowCount(len(services))
            for row, service in enumerate(services):
                self.services.setItem(row, SERVICE_NAME, QTableWidgetItem(service.name))
                self.services.setItem(row, SERVICE_PORT, QTableWidgetItem(str(service.port)))
                self.services.setCellWidget(
                    row,
                    SERVICE_PROTOCOL,
                    self._choice(Protocol, service.protocol.value, row, "service"),
                )
        finally:
            self._filling = False
        self.remove_service_button.setEnabled(bool(services))

    def _fill_rules(self, node_id: str) -> None:
        project = self.document.project
        node = project.node(node_id)
        rules = node.rules if node else ()
        self._filling = True
        try:
            self.rules.setRowCount(len(rules))
            for row, rule in enumerate(rules):
                self.rules.setCellWidget(
                    row,
                    RULE_ACTION,
                    self._choice(RuleAction, rule.action.value, row, "rule-action"),
                )
                self.rules.setItem(
                    row, RULE_FROM, QTableWidgetItem(reference_label(project, rule.source))
                )
                self.rules.setItem(
                    row, RULE_TO, QTableWidgetItem(reference_label(project, rule.destination))
                )
                self.rules.setCellWidget(
                    row,
                    RULE_PROTOCOL,
                    self._choice(RuleProtocol, rule.protocol.value, row, "rule-protocol"),
                )
                self.rules.setItem(
                    row, RULE_PORT, QTableWidgetItem("" if rule.port is None else str(rule.port))
                )
        finally:
            self._filling = False
        for button in (self.remove_rule_button, self.rule_up_button, self.rule_down_button):
            button.setEnabled(bool(rules))

    def _choice(self, options: type, current: str, row: int, kind: str) -> QComboBox:
        box = QComboBox()
        box.setObjectName(f"{kind}-{row}")
        for option in options:  # type: ignore[attr-defined]
            box.addItem(option.value)
        box.setCurrentText(current)
        box.currentTextChanged.connect(lambda _text, r=row, k=kind: self._choice_made(k, r))
        return box

    def _choice_made(self, kind: str, row: int) -> None:
        if self._filling:
            return
        if kind == "service":
            self._service_changed_row(row)
        else:
            self._rule_changed_row(row)

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

    def _cell(self, table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return item.text() if item is not None else ""

    def _combo(self, table: QTableWidget, row: int, column: int) -> str:
        widget = table.cellWidget(row, column)
        return widget.currentText() if isinstance(widget, QComboBox) else ""

    def _service_changed(self, item: QTableWidgetItem) -> None:
        if not self._filling:
            self._service_changed_row(item.row())

    def _service_changed_row(self, row: int) -> None:
        node_id = self.shown_node()
        if node_id is None:
            return

        def change(project: Project) -> Project:
            service = Service(
                self._cell(self.services, row, SERVICE_NAME).strip(),
                _port_number(self._cell(self.services, row, SERVICE_PORT)),
                Protocol(self._combo(self.services, row, SERVICE_PROTOCOL)),
            )
            return replace_service(project, node_id, row, service)

        self._edit("Change service", change)

    def add_service_row(self) -> None:
        node_id = self.shown_node()
        if node_id is None:
            return
        node = self.document.project.node(node_id)
        taken = {s.port for s in node.services} if node else set()
        port = next(p for p in range(8080, 65535) if p not in taken)
        self._edit("Add service", lambda p: add_service(p, node_id, "New service", port))

    def remove_service_row(self) -> None:
        node_id, row = self.shown_node(), self.services.currentRow()
        if node_id is None or row < 0:
            return
        self._edit("Remove service", lambda p: remove_service(p, node_id, row))

    def _rule_changed(self, item: QTableWidgetItem) -> None:
        if not self._filling:
            self._rule_changed_row(item.row())

    def _rule_changed_row(self, row: int) -> None:
        node_id = self.shown_node()
        if node_id is None:
            return

        def change(project: Project) -> Project:
            rule = Rule(
                RuleAction(self._combo(self.rules, row, RULE_ACTION)),
                parse_reference(project, self._cell(self.rules, row, RULE_FROM)),
                parse_reference(project, self._cell(self.rules, row, RULE_TO)),
                RuleProtocol(self._combo(self.rules, row, RULE_PROTOCOL)),
                parse_port(self._cell(self.rules, row, RULE_PORT)),
            )
            return replace_rule(project, node_id, row, rule)

        self._edit("Change rule", change)

    def add_rule_row(self) -> None:
        node_id = self.shown_node()
        if node_id is None:
            return
        self._edit("Add rule", lambda p: add_rule(p, node_id, Rule(RuleAction.ALLOW)))

    def remove_rule_row(self) -> None:
        node_id, row = self.shown_node(), self.rules.currentRow()
        if node_id is None or row < 0:
            return
        self._edit("Remove rule", lambda p: remove_rule(p, node_id, row))

    def move_rule_row(self, delta: int) -> None:
        node_id, row = self.shown_node(), self.rules.currentRow()
        if node_id is None or row < 0:
            return
        self._edit("Move rule", lambda p: move_rule(p, node_id, row, delta))
        self.rules.selectRow(row + delta)

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


def _port_number(text: str) -> int:
    number = parse_port(text)
    if number is None:
        raise ValueError("a service needs a port number")
    return number
