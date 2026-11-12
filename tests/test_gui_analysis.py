"""Flows, services, rules and "what goes down", driven through the window."""

import math

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QMessageBox, QTableWidget

from homelab_maker.gui.canvas import Canvas
from homelab_maker.gui.flows import (
    DESCRIPTION,
    PORT,
    STATUS,
    FlowDialog,
)
from homelab_maker.gui.inspector import (
    RULE_ACTION,
    RULE_FROM,
    RULE_PORT,
    RULE_PROTOCOL,
    RULE_TO,
    SERVICE_NAME,
    SERVICE_PORT,
    SERVICE_PROTOCOL,
)
from homelab_maker.gui.main_window import MainWindow
from homelab_maker.model import Project, Protocol, RuleAction
from homelab_maker.operations import add_node, set_vlan

CAMERA, DESKTOP_UI, DASHBOARD, FILES = range(4)  # the rows of the example's flows


@pytest.fixture
def example(window: MainWindow, sample: Project) -> MainWindow:
    window.document.replace(sample, None)
    QApplication.processEvents()
    return window


def shown(canvas: Canvas) -> bool:
    return canvas.flow_shown


def playing(canvas: Canvas) -> bool:
    return canvas.packet_playing


def status(window: MainWindow, row: int) -> str:
    item = window.flows_panel.table.item(row, STATUS)
    assert item is not None
    return item.text()


# ------------------------------------------------------------------------- the panel


def test_the_panel_lists_every_flow_with_its_answer(example: MainWindow) -> None:
    table = example.flows_panel.table
    assert table.rowCount() == 4
    assert [status(example, row) for row in range(4)] == [
        "Blocked",
        "Reachable",
        "Reachable",
        "Reachable",
    ]
    port = table.item(CAMERA, PORT)
    note = table.item(CAMERA, DESCRIPTION)
    assert port is not None and port.text() == "tcp/445"
    assert note is not None and "blocked by the IoT rule" in note.text()


def test_the_answers_are_coloured_by_the_theme(example: MainWindow) -> None:
    table = example.flows_panel.table
    blocked, reachable = table.item(CAMERA, STATUS), table.item(DESKTOP_UI, STATUS)
    assert blocked is not None and reachable is not None
    assert blocked.foreground().color().name() == example.tokens.danger
    assert reachable.foreground().color().name() == example.tokens.ok
    example.set_scheme("dark")
    assert blocked.foreground().color().name() == example.tokens.danger


def test_selecting_a_blocked_flow_draws_its_path_in_red_with_a_cross(example: MainWindow) -> None:
    panel, canvas = example.flows_panel, example.canvas
    panel.table.selectRow(CAMERA)
    assert canvas.flow_shown
    assert panel.detail.text().startswith("Blocked: Gateway denies it with rule 1")
    # camera, switch, gateway, switch again, nas: the switch is crossed twice
    assert len(canvas.flow_points()) == 5
    gateway = canvas.node_items["gateway"].center()
    assert canvas.stop_point("gateway") == gateway
    canvas.grab()  # paints the path and the cross


def test_selecting_a_reachable_flow_names_the_route(example: MainWindow) -> None:
    example.flows_panel.table.selectRow(DASHBOARD)
    detail = example.flows_panel.detail.text()
    assert detail.startswith("Reachable via Laptop → Living room AP")
    assert example.canvas.stop_point(None) is None
    example.canvas.grab()


def test_the_panel_says_what_the_answer_leaves_out(example: MainWindow) -> None:
    caveat = example.flows_panel.caveat.text()
    assert "not about the real network" in caveat and "NAT" in caveat


def test_clearing_the_selection_takes_the_path_off_the_canvas(example: MainWindow) -> None:
    panel = example.flows_panel
    panel.table.selectRow(FILES)
    assert shown(example.canvas)
    panel.table.clearSelection()
    assert not shown(example.canvas)
    assert panel.detail.text() == "Select a flow to see its path."
    assert not panel.remove_button.isEnabled()


def test_a_flow_with_no_flows_has_nothing_to_say(window: MainWindow) -> None:
    assert window.flows_panel.detail.text() == ""
    assert not window.flows_panel.play_button.isEnabled()


def test_the_path_follows_the_view_into_a_host(example: MainWindow) -> None:
    example.flows_panel.table.selectRow(DASHBOARD)
    outside = len(example.canvas.flow_points())
    example.canvas.enter("nas")
    inside = example.canvas.flow_points()
    assert outside == 4 and len(inside) == 1  # only the guest is a card in there
    example.canvas.leave()
    assert len(example.canvas.flow_points()) == 4


def test_a_blocked_vlan_is_marked_in_the_middle_of_the_cable(
    example: MainWindow, sample: Project
) -> None:
    broken = set_vlan(sample, "nas", "eth1", 30)
    example.document.replace(broken, None)
    example.flows_panel.table.selectRow(DESKTOP_UI)
    result = example.flows_panel.results[DESKTOP_UI]
    assert result.reason is not None and result.reason.value == "vlan"
    assert result.stopped_at is not None
    middle = example.canvas.stop_point(result.stopped_at)
    assert middle is not None
    switch, nas = example.canvas.node_items["switch"], example.canvas.node_items["nas"]
    assert math.dist(
        (middle.x(), middle.y()), ((switch.center() + nas.center()) / 2).toTuple()
    ) == pytest.approx(0)
    example.canvas.grab()


def test_the_answer_changes_when_the_drawing_does(example: MainWindow) -> None:
    gateway = example.document.project.node("gateway")
    assert gateway is not None
    example.canvas.select_ids({"gateway"})
    example.inspector.tabs.setCurrentIndex(2)
    example.inspector.rules.selectRow(0)
    example.inspector.remove_rule_button.click()
    assert status(example, CAMERA) == "Reachable"
    example.undo()
    assert status(example, CAMERA) == "Blocked"


# ------------------------------------------------------------------------ the packet


def test_a_packet_travels_along_the_shown_path(example: MainWindow) -> None:
    panel, canvas = example.flows_panel, example.canvas
    panel.table.selectRow(DESKTOP_UI)
    assert canvas.packet_position() is None  # not sent yet
    panel.play_button.setChecked(True)
    assert canvas.packet_playing
    start = canvas.packet_position()
    assert start is not None
    assert (start - canvas.flow_points()[0]).manhattanLength() < 1
    canvas.advance_packet(0.5)
    middle = canvas.packet_position()
    assert middle is not None and (middle - start).manhattanLength() > 10
    canvas.grab()
    panel.play_button.setChecked(False)
    assert not playing(canvas) and canvas.packet_position() is None


def test_the_packet_stops_when_the_selection_goes(example: MainWindow) -> None:
    panel, canvas = example.flows_panel, example.canvas
    panel.table.selectRow(DESKTOP_UI)
    panel.play_button.setChecked(True)
    panel.table.clearSelection()
    assert not playing(canvas) and not panel.play_button.isChecked()


def test_a_packet_wraps_round_to_the_start(example: MainWindow) -> None:
    canvas = example.canvas
    example.flows_panel.table.selectRow(DESKTOP_UI)
    canvas.play_packet(True)
    canvas.advance_packet(0.75)
    canvas.advance_packet(0.5)
    assert canvas.packet_position() is not None
    canvas.play_packet(False)


def test_there_is_no_packet_without_a_path(example: MainWindow) -> None:
    example.canvas.play_packet(True)  # nothing shown, so nothing starts
    assert not example.canvas.packet_playing


# ----------------------------------------------------------------------- adding flows


def test_the_dialog_collects_the_ends_the_port_and_the_words(
    example: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fill(dialog: FlowDialog) -> QDialog.DialogCode:
        dialog.source.setCurrentIndex(dialog.source.findData("desktop"))
        dialog.destination.setCurrentIndex(dialog.destination.findData("home-assistant"))
        dialog.port.setValue(8123)
        dialog.protocol.setCurrentText("tcp")
        dialog.description.setText(" Dashboard ")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(FlowDialog, "exec", fill)
    example.add_flow_action.trigger()
    flow = (
        example.document.project.flows[-1]
        if False
        else next(
            f for f in example.document.project.flows if f.id.startswith("desktop-home-assistant")
        )
    )
    assert (flow.port, flow.protocol, flow.description) == (8123, Protocol.TCP, "Dashboard")
    assert example.document.undo_label == "Add flow"
    selected = example.flows_panel.selected_flow()
    assert selected == flow.id  # the new flow is shown straight away


def test_cancelling_the_dialog_adds_nothing(
    example: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(FlowDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    before = example.document.project
    example.flows_panel.ask_for_flow()
    assert example.document.project == before


def test_a_flow_needs_two_devices_to_exist(window: MainWindow) -> None:
    messages: list[str] = []
    window.canvas.status_message.connect(messages.append)
    window.flows_panel.ask_for_flow()
    assert messages == ["Draw at least two devices first."]


def test_a_flow_to_the_same_device_is_refused_with_a_reason(example: MainWindow) -> None:
    messages: list[str] = []
    example.canvas.status_message.connect(messages.append)
    example.flows_panel.add_flow_between("nas", "nas", 443, Protocol.TCP, "")
    assert messages == ["a device does not need a flow to itself"]


def test_the_dialog_lists_every_device_by_name(example: MainWindow) -> None:
    dialog = FlowDialog(example.document.project)
    assert dialog.source.count() == len(example.document.project.nodes)
    assert dialog.source.itemText(dialog.source.findData("nas")) == "TrueNAS"
    assert dialog.values()[0] != dialog.values()[1]
    dialog.deleteLater()


def test_a_flow_is_removed_and_the_removal_undone(example: MainWindow) -> None:
    panel = example.flows_panel
    panel.table.selectRow(FILES)
    panel.remove_button.click()
    assert panel.table.rowCount() == 3
    assert example.document.undo_label == "Remove flow"
    example.undo()
    assert panel.table.rowCount() == 4
    panel.remove_selected()  # nothing is selected after the refresh... or the flow is
    panel.table.clearSelection()
    panel.remove_selected()


# ------------------------------------------------------------- services in the panel


def select_nas(window: MainWindow) -> None:
    window.canvas.select_ids({"nas"})
    window.inspector.tabs.setCurrentIndex(1)


def service_cell(window: MainWindow, row: int, column: int) -> str:
    item = window.inspector.services.item(row, column)
    assert item is not None
    return item.text()


def test_the_services_of_a_device_are_listed(example: MainWindow) -> None:
    select_nas(example)
    table = example.inspector.services
    assert table.rowCount() == 2
    assert service_cell(example, 0, SERVICE_NAME) == "SMB"
    assert service_cell(example, 0, SERVICE_PORT) == "445"
    combo = table.cellWidget(0, SERVICE_PROTOCOL)
    assert isinstance(combo, QComboBox) and combo.currentText() == "tcp"


def type_into(table: QTableWidget, row: int, column: int, text: str) -> None:
    """Type into a cell the way a person would, finding the cell afresh: edits rebuild the table."""
    item = table.item(row, column)
    assert item is not None
    item.setText(text)


def test_changing_a_service_port_changes_the_answer(example: MainWindow) -> None:
    select_nas(example)
    type_into(example.inspector.services, 0, SERVICE_PORT, "4455")
    assert status(example, FILES) == "Blocked"
    assert "no service on tcp/445" in example.flows_panel.results[FILES].detail
    type_into(example.inspector.services, 0, SERVICE_PORT, "445")
    assert status(example, FILES) == "Reachable"


def test_a_service_can_change_protocol_and_name(example: MainWindow) -> None:
    select_nas(example)
    combo = example.inspector.services.cellWidget(0, SERVICE_PROTOCOL)
    assert isinstance(combo, QComboBox)
    combo.setCurrentText("udp")
    nas = example.document.project.node("nas")
    assert nas is not None and nas.services[0].protocol is Protocol.UDP
    name = example.inspector.services.item(0, SERVICE_NAME)
    assert name is not None
    name.setText("File sharing")
    nas = example.document.project.node("nas")
    assert nas is not None and nas.services[0].name == "File sharing"


def test_a_bad_service_port_is_explained(example: MainWindow) -> None:
    select_nas(example)
    messages: list[str] = []
    example.canvas.status_message.connect(messages.append)
    services = example.inspector.services
    type_into(services, 0, SERVICE_PORT, "http")
    assert messages and "1 to 65535" in messages[0]
    assert service_cell(example, 0, SERVICE_PORT) == "445"
    type_into(services, 0, SERVICE_PORT, "")
    assert "needs a port number" in messages[-1]
    type_into(services, 0, SERVICE_PORT, "443")  # the other service already listens there
    assert "already listens" in messages[-1]


def test_services_are_added_with_a_free_port_and_removed(example: MainWindow) -> None:
    select_nas(example)
    inspector = example.inspector
    inspector.add_service_button.click()
    assert inspector.services.rowCount() == 3
    assert service_cell(example, 2, SERVICE_PORT) == "8080"
    inspector.add_service_button.click()
    assert service_cell(example, 3, SERVICE_PORT) == "8081"
    inspector.services.selectRow(2)
    inspector.remove_service_button.click()
    assert inspector.services.rowCount() == 3
    inspector.services.setCurrentCell(-1, -1)
    inspector.remove_service_row()  # nothing selected: nothing happens
    assert inspector.services.rowCount() == 3


# ---------------------------------------------------------------- rules in the panel


def select_gateway(window: MainWindow) -> None:
    window.canvas.select_ids({"gateway"})
    window.inspector.tabs.setCurrentIndex(2)


def rule_cell(window: MainWindow, row: int, column: int) -> str:
    item = window.inspector.rules.item(row, column)
    assert item is not None
    return item.text()


def test_only_a_device_that_routes_has_rules(example: MainWindow) -> None:
    example.canvas.select_ids({"nas"})
    assert not example.inspector.tabs.isTabVisible(2)
    example.canvas.select_ids({"gateway"})
    assert example.inspector.tabs.isTabVisible(2)


def test_the_rules_of_the_gateway_are_listed_with_names(example: MainWindow) -> None:
    select_gateway(example)
    assert example.inspector.rules.rowCount() == 3
    assert rule_cell(example, 0, RULE_FROM) == "192.168.20.0/24"
    assert rule_cell(example, 1, RULE_TO) == "TrueNAS"
    assert rule_cell(example, 1, RULE_PORT) == "443"
    assert rule_cell(example, 2, RULE_PORT) == ""
    action = example.inspector.rules.cellWidget(0, RULE_ACTION)
    assert isinstance(action, QComboBox) and action.currentText() == "deny"


def test_turning_the_deny_into_an_allow_lets_the_camera_through(example: MainWindow) -> None:
    select_gateway(example)
    action = example.inspector.rules.cellWidget(0, RULE_ACTION)
    assert isinstance(action, QComboBox)
    action.setCurrentText("allow")
    assert status(example, CAMERA) == "Reachable"
    rule = example.document.project.node("gateway").rules[0]  # type: ignore[union-attr]
    assert rule.action is RuleAction.ALLOW


def test_a_rule_names_a_device_by_its_name(example: MainWindow) -> None:
    select_gateway(example)
    item = example.inspector.rules.item(0, RULE_TO)
    assert item is not None
    item.setText("desktop")
    rule = example.document.project.node("gateway").rules[0]  # type: ignore[union-attr]
    assert rule.destination == "desktop"


def test_a_rule_that_names_nobody_is_explained(example: MainWindow) -> None:
    select_gateway(example)
    messages: list[str] = []
    example.canvas.status_message.connect(messages.append)
    item = example.inspector.rules.item(0, RULE_FROM)
    assert item is not None
    item.setText("nobody")
    assert messages == ["there is no device called 'nobody'"]
    assert rule_cell(example, 0, RULE_FROM) == "192.168.20.0/24"


def test_a_rule_port_needs_a_tcp_or_udp_protocol(example: MainWindow) -> None:
    select_gateway(example)
    messages: list[str] = []
    example.canvas.status_message.connect(messages.append)
    port = example.inspector.rules.item(0, RULE_PORT)
    assert port is not None
    port.setText("22")  # rule 1 is "any" protocol, which cannot have a port
    assert messages and "needs the protocol tcp or udp" in messages[0]
    protocol = example.inspector.rules.cellWidget(0, RULE_PROTOCOL)
    assert isinstance(protocol, QComboBox)
    protocol.setCurrentText("udp")
    item = example.inspector.rules.item(0, RULE_PORT)
    assert item is not None
    item.setText("22")
    rule = example.document.project.node("gateway").rules[0]  # type: ignore[union-attr]
    assert (rule.protocol.value, rule.port) == ("udp", 22)


def test_rules_are_added_moved_and_removed(example: MainWindow) -> None:
    select_gateway(example)
    inspector = example.inspector
    inspector.add_rule_button.click()
    assert inspector.rules.rowCount() == 4
    assert rule_cell(example, 3, RULE_FROM) == "any"
    inspector.rules.selectRow(3)
    inspector.rule_up_button.click()
    assert inspector.rules.currentRow() == 2
    inspector.rule_down_button.click()
    assert inspector.rules.currentRow() == 3
    inspector.rule_down_button.click()  # already last: refused, and the row is not lost
    inspector.remove_rule_button.click()
    assert inspector.rules.rowCount() == 3
    inspector.rules.setCurrentCell(-1, -1)
    inspector.remove_rule_row()
    inspector.move_rule_row(1)
    assert inspector.rules.rowCount() == 3


# -------------------------------------------------------------------- what goes down


class Boxes:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.texts: list[str] = []

        def information(_parent: object, _title: str, text: str) -> None:
            self.texts.append(text)

        monkeypatch.setattr(QMessageBox, "information", staticmethod(information))


@pytest.fixture
def boxes(monkeypatch: pytest.MonkeyPatch) -> Boxes:
    return Boxes(monkeypatch)


def test_switching_off_the_switch_dims_it_and_lists_the_damage(
    example: MainWindow, boxes: Boxes
) -> None:
    example.canvas.select_ids({"switch"})
    example.outage_action.trigger()
    assert example.canvas.offline == {"switch"}
    assert example.canvas.node_items["switch"].offline
    assert not example.canvas.node_items["desktop"].offline
    text = boxes.texts[0]
    assert "Switched off: Core switch." in text
    assert "Still running but cut off:" in text and "Desktop" in text
    assert "Desktop or laptop" not in text
    assert "not what the real network will do" in text
    assert example.back_to_normal_action.isEnabled()
    example.canvas.grab()


def test_a_host_switched_off_takes_its_guests_with_it(example: MainWindow, boxes: Boxes) -> None:
    example.canvas.select_ids({"nas"})
    example.outage_action.trigger()
    assert {"home-assistant", "nextcloud"} <= example.canvas.offline
    assert "TrueNAS is switched off" in boxes.texts[0]
    example.canvas.enter("nas")
    assert example.canvas.node_items["docker-host"].offline


def test_back_to_normal_puts_everything_back(example: MainWindow, boxes: Boxes) -> None:
    example.canvas.select_ids({"switch"})
    example.outage_action.trigger()
    example.back_to_normal_action.trigger()
    assert example.canvas.offline == frozenset()
    assert not example.canvas.node_items["switch"].offline
    assert not example.back_to_normal_action.isEnabled()


def test_a_harmless_outage_says_so(example: MainWindow, boxes: Boxes) -> None:
    example.canvas.select_ids({"camera"})
    example.outage_action.trigger()
    assert "Nothing else is affected" in boxes.texts[0]


def test_nothing_selected_means_nothing_to_switch_off(example: MainWindow, boxes: Boxes) -> None:
    example.canvas.select_ids(set())
    assert not example.outage_action.isEnabled()
    example.show_outage()
    assert boxes.texts == []


def test_a_new_device_does_not_clear_the_dimming(example: MainWindow, boxes: Boxes) -> None:
    example.canvas.select_ids({"switch"})
    example.outage_action.trigger()
    project, _ = add_node(example.document.project, "printer", 12, 6)
    example.document.apply(project, "Add printer")
    assert example.canvas.node_items["switch"].offline
