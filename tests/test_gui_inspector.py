"""The details panel, as someone using it would drive it."""

from PySide6.QtWidgets import QApplication

from homelab_maker.gui.main_window import MainWindow
from homelab_maker.operations import add_node, connect


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
        port, cable = table.item(row, 0), table.item(row, 1)
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
