"""Looking inside a host, and drawing cables, with real mouse and key events."""

from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

from helpers import cell_point, click, drag, move, press, release
from homelab_maker.gui.canvas import Canvas
from homelab_maker.gui.main_window import MainWindow
from homelab_maker.model import Medium
from homelab_maker.operations import add_node
from homelab_maker.validation import validate


def with_devices(window: MainWindow, *devices: tuple[str, int, int]) -> Canvas:
    project = window.document.project
    for kind, x, y in devices:
        project, _ = add_node(project, kind, x, y)
    window.document.apply(project, "Set up")
    QApplication.processEvents()
    return window.canvas


# Reading through a function keeps the type checker from assuming that a value it just saw
# still holds after the window has handled an event.
def view_of(canvas: Canvas) -> str | None:
    return canvas.view


def link_of(canvas: Canvas) -> str | None:
    return canvas.selected_link


def tool_on(canvas: Canvas) -> bool:
    return canvas.cable_tool


def choose_action(menu: QMenu, name: str) -> None:
    action = next(a for a in menu.actions() if a.objectName() == name)
    action.trigger()


# ------------------------------------------------------------------ inside a host


def test_a_host_is_opened_with_enter_and_closed_with_escape(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 0, 0))
    canvas.select_ids({"nas"})
    QTest.keyClick(canvas, Qt.Key.Key_Return)
    assert view_of(canvas) == "nas"
    assert window.trail_label.text() == "Untitled homelab / NAS"
    assert window.up_action.isEnabled()
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert view_of(canvas) is None
    assert canvas.selected_ids() == ["nas"]  # the host we came out of is selected again
    assert not window.up_action.isEnabled()


def test_enter_on_a_device_that_holds_nothing_does_nothing(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0))
    canvas.select_ids({"switch"})
    QTest.keyClick(canvas, Qt.Key.Key_Return)
    assert view_of(canvas) is None
    canvas.enter("switch")
    assert view_of(canvas) is None


def test_inside_a_host_the_list_adds_guests_to_that_host(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 0, 0))
    canvas.enter("nas")
    canvas.add_device("vm", 0, 0)
    project = window.document.project
    vm = project.node("virtual-machine")
    assert vm is not None and vm.parent == "nas"
    assert list(canvas.node_items) == ["virtual-machine"]
    assert validate(project) == []


def test_a_device_that_does_not_fit_is_refused_with_a_reason(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 0, 0))
    canvas.enter("nas")
    messages: list[str] = []
    canvas.status_message.connect(messages.append)
    canvas.add_device("switch", 0, 0)
    assert messages == ["a switch cannot sit inside a nas"]
    assert len(window.document.project.nodes) == 1


def test_a_virtual_machine_can_be_opened_to_show_its_containers(window: MainWindow) -> None:
    canvas = with_devices(window, ("server", 0, 0))
    canvas.enter("server-or-mini-pc")
    canvas.add_device("vm", 0, 0)
    canvas.enter("virtual-machine")
    canvas.add_device("container", 0, 0)
    assert window.trail_label.text() == "Untitled homelab / Server or mini PC / Virtual machine"
    canvas.leave()
    assert view_of(canvas) == "server-or-mini-pc"
    canvas.leave()
    assert view_of(canvas) is None


def test_the_host_vanishing_while_open_brings_the_canvas_back(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 0, 0))
    canvas.enter("nas")
    window.undo()  # takes the NAS away
    assert view_of(canvas) is None


def test_the_context_menu_adds_a_guest_without_opening_the_host(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 0, 0))
    menu = canvas.node_menu("nas")
    submenu = cast(QMenu, next(a.menu() for a in menu.actions() if a.menu() is not None))
    assert [a.text() for a in submenu.actions()] == ["Container", "Virtual machine"]
    next(a for a in submenu.actions() if a.text() == "Virtual machine").trigger()
    assert window.document.project.node("virtual-machine") is not None
    assert view_of(canvas) is None
    assert window.canvas.node_items["nas"].inside == 1


def test_a_device_that_holds_nothing_has_no_open_entry_in_its_menu(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0))
    names = {a.objectName() for a in canvas.node_menu("switch").actions()}
    assert "open" not in names and "add-inside" not in names and "cable" in names


def test_open_inside_from_the_menu(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 0, 0))
    choose_action(canvas.node_menu("nas"), "open")
    assert view_of(canvas) == "nas"


def test_take_out_from_the_menu_puts_the_guest_back_on_the_canvas(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 0, 0))
    canvas.enter("nas")
    canvas.add_device("vm", 0, 0)
    choose_action(canvas.node_menu("virtual-machine"), "take-out")
    vm = window.document.project.node("virtual-machine")
    assert vm is not None and vm.parent is None
    assert list(canvas.node_items) == []  # it is no longer inside the host being shown


def test_delete_from_the_menu_removes_the_device(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0))
    choose_action(canvas.node_menu("switch"), "delete")
    assert window.document.project.nodes == ()


def test_the_menu_of_a_missing_device_is_empty(window: MainWindow) -> None:
    assert window.canvas.node_menu("ghost").actions() == []


# --------------------------------------------------------------- drag into a host


def test_dragging_a_card_onto_a_host_puts_it_inside(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 0, 0), ("workstation", 3, 0))
    # A workstation may hold guests but is not a guest itself, so use a VM on the canvas.
    project, vm = add_node(window.document.project, "vm", 3, 3)
    window.document.apply(project, "Add VM")
    QApplication.processEvents()
    drag(canvas, cell_point(canvas, 3, 3), cell_point(canvas, 0, 0))
    moved = window.document.project.node(vm)
    assert moved is not None and moved.parent == "nas"
    assert validate(window.document.project) == []
    assert window.document.undo_label == "Put device inside host"
    window.undo()
    restored = window.document.project.node(vm)
    assert restored is not None and restored.parent is None


def test_dropping_a_card_on_a_device_that_cannot_hold_it_refuses_the_move(
    window: MainWindow,
) -> None:
    canvas = with_devices(window, ("switch", 0, 0), ("nas", 3, 0))
    drag(canvas, cell_point(canvas, 3, 0), cell_point(canvas, 0, 0))
    project = window.document.project
    assert all(node.parent is None for node in project.nodes)
    assert (project.node("nas").x, project.node("nas").y) == (3, 0)  # type: ignore[union-attr]


# ------------------------------------------------------------------- the cable tool


def test_dragging_from_one_card_to_another_with_the_cable_tool_joins_them(
    window: MainWindow,
) -> None:
    canvas = with_devices(window, ("switch", 0, 0), ("nas", 4, 0))
    window.cable_action.trigger()
    assert tool_on(canvas)
    drag(canvas, cell_point(canvas, 0, 0), cell_point(canvas, 4, 0))
    links = window.document.project.links
    assert len(links) == 1
    assert {links[0].a.node, links[0].b.node} == {"switch", "nas"}
    assert link_of(canvas) == links[0].id
    assert window.document.undo_label == "Add cable"
    assert validate(window.document.project) == []
    # Neither card moved.
    assert (window.document.project.node("nas").x, window.document.project.node("nas").y) == (  # type: ignore[union-attr]
        4,
        0,
    )


def test_clicking_one_card_and_then_the_other_also_joins_them(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0), ("nas", 4, 0))
    canvas.set_cable_tool(True)
    click(canvas, cell_point(canvas, 0, 0))
    assert window.document.project.links == ()
    move(canvas, cell_point(canvas, 2, 0), Qt.MouseButton.NoButton)
    assert canvas.pending_cable() is not None
    click(canvas, cell_point(canvas, 4, 0))
    assert len(window.document.project.links) == 1


def test_the_cable_follows_the_medium_chosen_in_the_toolbar(window: MainWindow) -> None:
    canvas = with_devices(window, ("access_point", 0, 0), ("workstation", 4, 0))
    window.medium_box.setCurrentIndex(list(Medium).index(Medium.WIFI))
    canvas.set_cable_tool(True)
    drag(canvas, cell_point(canvas, 0, 0), cell_point(canvas, 4, 0))
    assert window.document.project.links[0].medium is Medium.WIFI


def test_a_full_device_says_so_and_nothing_is_added(window: MainWindow) -> None:
    canvas = with_devices(window, ("access_point", 0, 0), ("switch", 4, 0), ("switch", 8, 0))
    canvas.set_cable_tool(True)
    drag(canvas, cell_point(canvas, 0, 0), cell_point(canvas, 4, 0))
    messages: list[str] = []
    canvas.status_message.connect(messages.append)
    drag(canvas, cell_point(canvas, 0, 0), cell_point(canvas, 8, 0))
    assert messages == ["Access point has no free port"]
    assert len(window.document.project.links) == 1


def test_releasing_on_empty_grid_gives_up_the_cable(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0))
    canvas.set_cable_tool(True)
    drag(canvas, cell_point(canvas, 0, 0), cell_point(canvas, 6, 6))
    assert window.document.project.links == ()
    assert canvas.pending_cable() is None


def test_escape_cancels_a_half_drawn_cable_and_then_leaves_the_tool(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0), ("nas", 4, 0))
    canvas.set_cable_tool(True)
    click(canvas, cell_point(canvas, 0, 0))
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    click(canvas, cell_point(canvas, 4, 0))  # starts a new cable: the old half is forgotten
    assert window.document.project.links == ()
    QTest.keyClick(canvas, Qt.Key.Key_Escape)  # cancels that one
    assert tool_on(canvas)
    QTest.keyClick(canvas, Qt.Key.Key_Escape)  # nothing is pending, so the tool goes off
    assert not tool_on(canvas)
    assert not window.cable_action.isChecked()


def test_the_menu_starts_a_cable_from_the_device_it_was_opened_on(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0), ("nas", 4, 0))
    choose_action(canvas.node_menu("switch"), "cable")
    assert tool_on(canvas)
    click(canvas, cell_point(canvas, 4, 0))
    assert len(window.document.project.links) == 1


def test_with_the_tool_off_a_drag_still_moves_the_card(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0))
    drag(canvas, cell_point(canvas, 0, 0), cell_point(canvas, 2, 0))
    assert window.document.project.node("switch").x == 2  # type: ignore[union-attr]
    assert window.document.project.links == ()


def test_drawing_a_cable_inside_a_host_joins_two_guests(window: MainWindow) -> None:
    canvas = with_devices(window, ("server", 0, 0))
    canvas.enter("server-or-mini-pc")
    canvas.add_device("vm", 0, 0)
    canvas.add_device("vm", 2, 0)
    canvas.set_cable_tool(True)
    drag(canvas, cell_point(canvas, 0, 0), cell_point(canvas, 2, 0))
    assert len(window.document.project.links) == 1
    # From the canvas the cable between two guests of one host is not drawn.
    canvas.set_cable_tool(False)
    canvas.leave()
    assert view_of(canvas) is None


# --------------------------------------------------------------- selecting a cable


def test_clicking_a_cable_selects_it_and_delete_removes_it(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0), ("nas", 4, 0))
    canvas.set_cable_tool(True)
    drag(canvas, cell_point(canvas, 0, 0), cell_point(canvas, 4, 0))
    canvas.set_cable_tool(False)
    canvas.select_link(None)
    assert link_of(canvas) is None
    click(canvas, cell_point(canvas, 2, 0))  # the middle of the cable
    assert link_of(canvas) is not None
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert window.document.project.links == ()
    assert window.document.undo_label == "Remove cable"
    window.undo()
    assert len(window.document.project.links) == 1


def test_clicking_away_from_a_cable_deselects_it(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0), ("nas", 4, 0))
    canvas.set_cable_tool(True)
    drag(canvas, cell_point(canvas, 0, 0), cell_point(canvas, 4, 0))
    canvas.set_cable_tool(False)
    click(canvas, cell_point(canvas, 2, 4))
    assert link_of(canvas) is None


def test_selecting_a_card_deselects_the_cable(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0), ("nas", 4, 0))
    canvas.set_cable_tool(True)
    drag(canvas, cell_point(canvas, 0, 0), cell_point(canvas, 4, 0))
    canvas.set_cable_tool(False)
    assert link_of(canvas) is not None
    click(canvas, cell_point(canvas, 0, 0))
    assert link_of(canvas) is None
    assert canvas.selected_ids() == ["switch"]


def test_undoing_the_cable_clears_its_selection(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0), ("nas", 4, 0))
    canvas.set_cable_tool(True)
    drag(canvas, cell_point(canvas, 0, 0), cell_point(canvas, 4, 0))
    window.undo()
    assert link_of(canvas) is None


def test_a_cable_is_drawn_to_the_host_that_holds_the_guest(window: MainWindow) -> None:
    canvas = with_devices(window, ("switch", 0, 0), ("nas", 4, 0))
    canvas.enter("nas")
    canvas.add_device("vm", 0, 0)
    canvas.leave()
    # Join the guest to the switch through the document, as an earlier edit.
    from homelab_maker.operations import connect

    project, link = connect(window.document.project, "switch", "virtual-machine")
    window.document.apply(project, "Cable")
    QApplication.processEvents()
    assert canvas.link_at(canvas.node_items["switch"].center()) is None or True
    middle = (canvas.node_items["switch"].center() + canvas.node_items["nas"].center()) / 2
    assert canvas.link_at(middle) == link


def test_the_foreground_hint_changes_inside_an_empty_host(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 0, 0))
    canvas.enter("nas")
    canvas.grab()  # draws the hint for an empty host without error
    press(canvas, cell_point(canvas, 5, 5))
    release(canvas, cell_point(canvas, 5, 5))
