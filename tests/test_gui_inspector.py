"""The details panel, as someone using it would drive it."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QTableWidgetItem

from homelab_maker.gui.inspector import ADDRESSES, CABLE, MODE, PORT, TAGGED, VLAN
from homelab_maker.gui.main_window import MainWindow
from homelab_maker.model import Interface, InterfaceMode
from homelab_maker.operations import add_node, connect, set_addresses


def cabled_window(window: MainWindow) -> MainWindow:
    project, _ = add_node(window.document.project, "switch", 0, 0)
    project, _ = add_node(project, "nas", 4, 0)
    project, _ = connect(project, "switch", "nas")
    window.document.apply(project, "Set up")
    QApplication.processEvents()
    return window


def port_texts(window: MainWindow) -> list[tuple[str, str]]:
    table = window.inspector.ports
    result = []
    for row in range(table.rowCount()):
        port, cable = table.item(row, PORT), table.item(row, CABLE)
        assert port is not None and cable is not None
        result.append((port.text(), cable.text()))
    return result


def test_with_nothing_selected_it_says_so(window: MainWindow) -> None:
    assert window.inspector.title.text() == "Nothing selected"
    assert not window.inspector.ports.isVisibleTo(window.inspector)


def test_a_selected_device_lists_its_ports_and_what_is_plugged_in(window: MainWindow) -> None:
    cabled_window(window)
    window.canvas.select_ids({"switch"})
    inspector = window.inspector
    assert inspector.title.text() == "Switch"
    assert inspector.subtitle.text() == "Switch, on the canvas"
    ports = port_texts(window)
    assert len(ports) == 8
    assert ports[0] == ("port1", "NAS · eth1")
    assert ports[1] == ("port2", "—")


def test_a_guest_says_which_host_it_is_inside(window: MainWindow) -> None:
    project, _ = add_node(window.document.project, "nas", 0, 0)
    project, _ = add_node(project, "vm", 0, 0, parent="nas")
    window.document.apply(project, "Set up")
    window.canvas.enter("nas")
    window.canvas.select_ids({"virtual-machine"})
    assert window.inspector.subtitle.text() == "Virtual machine, inside NAS"


def test_several_selected_devices_are_counted_not_listed(window: MainWindow) -> None:
    cabled_window(window)
    window.canvas.select_all()
    assert window.inspector.title.text() == "2 devices selected"
    assert not window.inspector.ports.isVisibleTo(window.inspector)


def test_adding_a_port_is_one_undoable_step(window: MainWindow) -> None:
    cabled_window(window)
    window.canvas.select_ids({"nas"})
    window.inspector.add_port_button.click()
    assert [name for name, _ in port_texts(window)] == ["eth1", "eth2", "eth3"]
    assert window.document.undo_label == "Add port"
    window.undo()
    assert len(port_texts(window)) == 2


def test_a_cable_is_removed_from_the_row_that_holds_it(window: MainWindow) -> None:
    cabled_window(window)
    window.canvas.select_ids({"switch"})
    inspector = window.inspector
    assert not inspector.disconnect_button.isEnabled()
    inspector.ports.selectRow(0)
    assert inspector.disconnect_button.isEnabled()
    inspector.disconnect_button.click()
    assert window.document.project.links == ()
    assert window.document.undo_label == "Remove cable"
    assert port_texts(window)[0] == ("port1", "—")


def test_a_free_port_cannot_be_unplugged(window: MainWindow) -> None:
    cabled_window(window)
    window.canvas.select_ids({"switch"})
    window.inspector.ports.selectRow(3)
    assert not window.inspector.disconnect_button.isEnabled()
    window.inspector.remove_selected_cable()  # does nothing
    assert len(window.document.project.links) == 1


def test_a_selected_cable_is_described_and_can_be_removed(window: MainWindow) -> None:
    cabled_window(window)
    window.canvas.select_link(window.document.project.links[0].id)
    inspector = window.inspector
    assert inspector.title.text() == "Cable"
    assert inspector.cable_text.text() == "NAS · eth1 — Switch · port1 (ethernet)"
    inspector.remove_cable_button.click()
    assert window.document.project.links == ()
    assert inspector.title.text() == "Nothing selected"


def test_adding_a_port_with_nothing_selected_does_nothing(window: MainWindow) -> None:
    window.inspector.add_port()
    assert window.document.project.nodes == ()


# ------------------------------------------------------------------- editing a port


def cell(window: MainWindow, row: int, column: int) -> QTableWidgetItem:
    item = window.inspector.ports.item(row, column)
    assert item is not None
    return item


def interface_of(window: MainWindow, row: int) -> Interface:
    node = window.document.project.node("switch")
    assert node is not None
    return node.interfaces[row]


def selected_switch(window: MainWindow) -> MainWindow:
    project, _ = add_node(window.document.project, "switch", 0, 0)
    window.document.apply(project, "Set up")
    window.canvas.select_ids({"switch"})
    return window


def mode_box(window: MainWindow, row: int) -> QComboBox:
    widget = window.inspector.ports.cellWidget(row, MODE)
    assert isinstance(widget, QComboBox)
    return widget


def test_typing_addresses_sets_them_as_one_undoable_step(window: MainWindow) -> None:
    selected_switch(window)
    cell(window, 0, ADDRESSES).setText("192.168.1.2/24, fd00::2/64")
    assert interface_of(window, 0).addresses == ("192.168.1.2/24", "fd00::2/64")
    assert window.document.undo_label == "Change addresses"
    window.undo()
    assert interface_of(window, 0).addresses == ()


def test_a_bad_address_is_explained_and_the_cell_goes_back(window: MainWindow) -> None:
    selected_switch(window)
    messages: list[str] = []
    window.canvas.status_message.connect(messages.append)
    cell(window, 0, ADDRESSES).setText("banana")
    assert messages and "not an IPv4 or IPv6 address" in messages[0]
    assert cell(window, 0, ADDRESSES).text() == ""
    assert window.document.undo_label == "Set up"


def test_typing_a_vlan_sets_it_and_an_empty_cell_clears_it(window: MainWindow) -> None:
    selected_switch(window)
    cell(window, 1, VLAN).setText("20")
    assert interface_of(window, 1).vlan == 20
    cell(window, 1, VLAN).setText("")
    assert interface_of(window, 1).vlan is None


def test_a_vlan_that_is_not_a_number_is_refused(window: MainWindow) -> None:
    selected_switch(window)
    messages: list[str] = []
    window.canvas.status_message.connect(messages.append)
    cell(window, 0, VLAN).setText("ten")
    assert messages == ["'ten' is not a VLAN number"]
    assert cell(window, 0, VLAN).text() == ""


def test_a_port_becomes_a_trunk_and_then_takes_tagged_vlans(window: MainWindow) -> None:
    selected_switch(window)
    assert not cell(window, 0, TAGGED).flags() & Qt.ItemFlag.ItemIsEditable
    mode_box(window, 0).setCurrentText("trunk")
    assert cell(window, 0, TAGGED).flags() & Qt.ItemFlag.ItemIsEditable
    cell(window, 0, TAGGED).setText("10, 30-32")
    port = interface_of(window, 0)
    assert port.mode is InterfaceMode.TRUNK and port.trunk_vlans == (10, 30, 31, 32)
    assert cell(window, 0, TAGGED).text() == "10, 30-32"
    mode_box(window, 0).setCurrentText("access")
    assert interface_of(window, 0).trunk_vlans == ()


def test_renaming_a_port_through_the_table(window: MainWindow) -> None:
    selected_switch(window)
    cell(window, 0, PORT).setText("uplink")
    assert interface_of(window, 0).name == "uplink"
    cell(window, 1, PORT).setText("uplink")  # already taken
    assert interface_of(window, 1).name == "port2"
    assert cell(window, 1, PORT).text() == "port2"


def test_a_free_port_can_be_removed_and_a_cabled_one_cannot(window: MainWindow) -> None:
    cabled_window(window)
    window.canvas.select_ids({"switch"})
    inspector = window.inspector
    messages: list[str] = []
    window.canvas.status_message.connect(messages.append)
    inspector.ports.selectRow(0)
    inspector.remove_port_button.click()
    assert messages and "remove the cable first" in messages[0]
    inspector.ports.selectRow(7)
    inspector.remove_port_button.click()
    node = window.document.project.node("switch")
    assert node is not None and len(node.interfaces) == 7


def test_removing_a_port_with_none_selected_does_nothing(window: MainWindow) -> None:
    selected_switch(window)
    window.inspector.ports.setCurrentCell(-1, -1)
    window.inspector.remove_selected_port()
    node = window.document.project.node("switch")
    assert node is not None and len(node.interfaces) == 8


def test_the_selected_row_survives_an_edit(window: MainWindow) -> None:
    selected_switch(window)
    window.inspector.ports.selectRow(2)
    cell(window, 2, VLAN).setText("30")
    assert window.inspector.ports.currentRow() == 2


# ------------------------------------------------------------------------- the checks


def test_the_checks_panel_lists_findings_and_counts_them(window: MainWindow) -> None:
    selected_switch(window)
    panel = window.findings
    assert panel.summary.text() == "1 warning, 0 notes"
    assert "Switch has no cable or link" in panel.list.item(0).text()
    project, _ = add_node(window.document.project, "nas", 4, 0)
    window.document.apply(project, "Add NAS")
    assert panel.summary.text() == "2 warnings, 0 notes"
    assert "2 warnings" in window._counts.text()


def test_an_empty_homelab_has_nothing_to_report(window: MainWindow) -> None:
    assert window.findings.summary.text() == "Nothing to report."


def test_activating_a_finding_goes_to_the_device(window: MainWindow) -> None:
    project, _ = add_node(window.document.project, "nas", 0, 0)
    project, _ = add_node(project, "switch", 4, 0)
    project, _ = connect(project, "nas", "switch")
    project = set_addresses(project, "nas", "eth1", ["10.0.0.5/24"])
    project = set_addresses(project, "switch", "port1", ["10.0.0.5/24"])
    window.document.apply(project, "Same address twice")
    item = window.findings.list.item(0)
    assert "10.0.0.5" in item.text()
    window.findings.list.itemActivated.emit(item)
    assert window.canvas.selected_ids() in (["nas"], ["switch"])


def test_a_device_inside_a_host_is_revealed_by_opening_the_host(window: MainWindow) -> None:
    project, _ = add_node(window.document.project, "nas", 0, 0)
    project, _ = add_node(project, "vm", 0, 0, parent="nas")
    window.document.apply(project, "Set up")
    window.canvas.reveal("virtual-machine")
    assert window.canvas.view == "nas"
    assert window.canvas.selected_ids() == ["virtual-machine"]
    window.canvas.reveal("ghost")  # nothing happens
    assert window.canvas.selected_ids() == ["virtual-machine"]


def test_the_checks_use_the_colours_of_the_current_theme(window: MainWindow) -> None:
    selected_switch(window)
    window.set_scheme("dark")
    assert window.findings.list.item(0).foreground().color().name() == "#fbbf24"
