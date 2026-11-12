"""The flows panel: what is meant to talk to what, and whether the drawing lets it.

Every flow is analysed each time the drawing changes. Selecting one draws its path on the
canvas, green when it gets through and red, with a cross where it stops, when it does not.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from homelab_maker.document import Document
from homelab_maker.gui.canvas import Canvas
from homelab_maker.gui.theme import Tokens
from homelab_maker.model import Project, Protocol
from homelab_maker.operations import add_flow, remove_flows
from homelab_maker.reachability import NOT_MODELLED, Result, analyse_all

STATUS, SOURCE, DESTINATION, PORT, DESCRIPTION = range(5)
_HEADERS = ["Result", "From", "To", "Port", "What for"]


class FlowDialog(QDialog):
    """Asks for the two ends, the port and a few words about a new flow."""

    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add a flow")
        self.source = QComboBox()
        self.destination = QComboBox()
        for node in project.nodes:
            self.source.addItem(node.name, node.id)
            self.destination.addItem(node.name, node.id)
        if self.destination.count() > 1:
            self.destination.setCurrentIndex(1)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(443)
        self.protocol = QComboBox()
        for protocol in Protocol:
            self.protocol.addItem(protocol.value)
        self.description = QLineEdit()
        self.description.setPlaceholderText("for example: web interface")

        form = QFormLayout()
        form.addRow("From", self.source)
        form.addRow("To", self.destination)
        form.addRow("Port", self.port)
        form.addRow("Protocol", self.protocol)
        form.addRow("What for", self.description)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, int, Protocol, str]:
        return (
            str(self.source.currentData()),
            str(self.destination.currentData()),
            self.port.value(),
            Protocol(self.protocol.currentText()),
            self.description.text(),
        )


class FlowsPanel(QWidget):
    # The result of the selected flow (or None), for the window to draw on the canvas.
    flow_selected = Signal(object)

    def __init__(
        self, document: Document, canvas: Canvas, tokens: Tokens, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("flows")
        self.document = document
        self.canvas = canvas
        self.tokens = tokens
        self.results: tuple[Result, ...] = ()
        self._filling = False

        self.table = QTableWidget(0, len(_HEADERS))
        self.table.setObjectName("flows-table")
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)

        self.add_button = QPushButton("Add flow…")
        self.add_button.clicked.connect(self.ask_for_flow)
        self.remove_button = QPushButton("Remove flow")
        self.remove_button.clicked.connect(self.remove_selected)
        self.play_button = QPushButton("Send a packet")
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(self.canvas.play_packet)

        self.detail = QLabel()
        self.detail.setObjectName("flow-detail")
        self.detail.setWordWrap(True)
        self.caveat = QLabel(
            "The answer is about the drawing, not about the real network. "
            "Not modelled: " + "; ".join(NOT_MODELLED) + "."
        )
        self.caveat.setObjectName("flow-caveat")
        small = self.caveat.font()
        small.setPointSizeF(small.pointSizeF() - 1)
        self.caveat.setFont(small)
        self.caveat.setWordWrap(True)

        buttons = QHBoxLayout()
        for button in (self.add_button, self.remove_button, self.play_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.detail)
        layout.addWidget(self.caveat)

        self.document.subscribe(self.refresh)
        self.refresh()

    def set_tokens(self, tokens: Tokens) -> None:
        self.tokens = tokens
        self._colour()

    # ----------------------------------------------------------------------- showing

    def selected_flow(self) -> str | None:
        row = self.table.currentRow()
        if 0 <= row < len(self.results) and self.table.selectedItems():
            return self.results[row].flow
        return None

    def refresh(self) -> None:
        keep = self.selected_flow()
        project = self.document.project
        self.results = analyse_all(project)
        flows = {flow.id: flow for flow in project.flows}
        self._filling = True
        try:
            self.table.setRowCount(len(self.results))
            for row, result in enumerate(self.results):
                flow = flows[result.flow]
                names = {n.id: n.name for n in project.nodes}
                cells = {
                    STATUS: "Reachable" if result.reachable else "Blocked",
                    SOURCE: names.get(flow.source, flow.source),
                    DESTINATION: names.get(flow.destination, flow.destination),
                    PORT: f"{flow.protocol.value}/{flow.port}",
                    DESCRIPTION: flow.description,
                }
                for column, text in cells.items():
                    item = QTableWidgetItem(text)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setToolTip(result.detail)
                    self.table.setItem(row, column, item)
            self._colour()
            if keep is not None:
                row = next((i for i, r in enumerate(self.results) if r.flow == keep), -1)
                if row >= 0:
                    self.table.selectRow(row)
        finally:
            self._filling = False
        self._selection_changed()

    def _colour(self) -> None:
        for row, result in enumerate(self.results):
            item = self.table.item(row, STATUS)
            if item is not None:
                colour = self.tokens.ok if result.reachable else self.tokens.danger
                item.setForeground(QBrush(QColor(colour)))

    def _selection_changed(self) -> None:
        if self._filling:
            return
        flow_id = self.selected_flow()
        result = next((r for r in self.results if r.flow == flow_id), None)
        self.remove_button.setEnabled(result is not None)
        self.play_button.setEnabled(result is not None)
        if result is None:
            self.detail.setText("Select a flow to see its path." if self.results else "")
            self.canvas.clear_flow()
            self.play_button.setChecked(False)
        else:
            text = ("Reachable " if result.reachable else "Blocked: ") + result.detail
            if result.notes:
                text += ". " + "; ".join(result.notes)
            self.detail.setText(text)
            self.canvas.show_flow(result.path, result.reachable, result.stopped_at)
            self.canvas.play_packet(self.play_button.isChecked())
        self.flow_selected.emit(result)

    # ----------------------------------------------------------------------- editing

    def ask_for_flow(self) -> None:
        project = self.document.project
        if len(project.nodes) < 2:
            self.canvas.status_message.emit("Draw at least two devices first.")
            return
        dialog = FlowDialog(project, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.add_flow_between(*dialog.values())

    def add_flow_between(
        self, source: str, destination: str, port: int, protocol: Protocol, description: str
    ) -> None:
        try:
            project, flow_id = add_flow(
                self.document.project, source, destination, port, protocol, description
            )
        except ValueError as exc:
            self.canvas.status_message.emit(str(exc))
            return
        self.document.apply(project, "Add flow")
        row = next((i for i, r in enumerate(self.results) if r.flow == flow_id), -1)
        if row >= 0:
            self.table.selectRow(row)

    def remove_selected(self) -> None:
        flow_id = self.selected_flow()
        if flow_id is None:
            return
        self.document.apply(remove_flows(self.document.project, [flow_id]), "Remove flow")
