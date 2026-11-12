"""Zones and the name of the homelab: the operations, and the menu entries that use them."""

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog

from homelab_maker.gui.main_window import MainWindow
from homelab_maker.model import Project
from homelab_maker.operations import (
    add_node,
    remove_zone,
    rename_project,
    rename_zone,
    zone_around,
)
from homelab_maker.validation import validate


def three() -> Project:
    project = Project()
    for kind, x, y in [("nas", 1, 1), ("switch", 4, 1), ("server", 2, 3)]:
        project, _ = add_node(project, kind, x, y)
    return project


# ------------------------------------------------------------------------ operations


def test_a_zone_covers_the_cells_of_the_chosen_devices() -> None:
    project, zone_id = zone_around(three(), ["nas", "switch"], "Servers")
    zone = project.zones[0]
    assert zone.id == zone_id == "servers"
    assert (zone.x, zone.y, zone.width, zone.height) == (1, 1, 4, 1)
    assert validate(project) == []


def test_a_margin_widens_it_on_every_side() -> None:
    project, _ = zone_around(three(), ["nas", "switch", "server-or-mini-pc"], "All", margin=1)
    zone = project.zones[0]
    assert (zone.x, zone.y, zone.width, zone.height) == (0, 0, 6, 5)


def test_a_zone_needs_devices_a_name_and_the_canvas() -> None:
    with pytest.raises(ValueError, match="choose the devices"):
        zone_around(three(), [], "X")
    with pytest.raises(ValueError, match="needs a name"):
        zone_around(three(), ["nas"], "   ")
    project, _ = add_node(three(), "vm", 0, 0, parent="nas")
    with pytest.raises(ValueError, match="inside a host"):
        zone_around(project, ["virtual-machine"], "X")


def test_two_zones_with_one_name_get_different_ids() -> None:
    project, first = zone_around(three(), ["nas"], "LAN")
    project, second = zone_around(project, ["switch"], "LAN")
    assert first != second and len(project.zones) == 2


def test_a_zone_is_renamed_and_removed() -> None:
    project, zone_id = zone_around(three(), ["nas"], "LAN")
    project = rename_zone(project, zone_id, " Home ")
    assert project.zones[0].name == "Home"
    assert remove_zone(project, zone_id).zones == ()
    with pytest.raises(ValueError, match="there is no zone 'nope'"):
        remove_zone(project, "nope")
    with pytest.raises(ValueError, match="there is no zone 'nope'"):
        rename_zone(project, "nope", "x")


def test_the_homelab_is_renamed() -> None:
    assert rename_project(Project(), " My lab ").name == "My lab"
    with pytest.raises(ValueError, match="must not be empty"):
        rename_project(Project(), "  ")


# ----------------------------------------------------------------------------- menu


@pytest.fixture
def lab(window: MainWindow) -> MainWindow:
    window.document.replace(three(), None)
    QApplication.processEvents()
    return window


def answer_text(monkeypatch: pytest.MonkeyPatch, text: str, accepted: bool = True) -> None:
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (text, accepted)))


def test_a_zone_is_drawn_around_the_selection(
    lab: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    lab.canvas.select_ids({"nas", "switch"})
    answer_text(monkeypatch, "Servers")
    lab.add_zone_action.trigger()
    zone = lab.document.project.zones[0]
    assert zone.name == "Servers" and (zone.x, zone.y) == (0, 0)  # margin of one cell
    assert lab.document.undo_label == "Add zone"
    lab.undo()
    assert lab.document.project.zones == ()


def test_the_zone_entry_needs_a_selection_and_a_name(
    lab: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    lab.canvas.select_ids(set())
    assert not lab.add_zone_action.isEnabled()
    lab.add_zone()  # called anyway: it explains instead of doing nothing silently
    assert "Select the devices" in lab.statusBar().currentMessage()
    lab.canvas.select_ids({"nas"})
    answer_text(monkeypatch, "  ")
    lab.add_zone()
    assert "needs a name" in lab.statusBar().currentMessage()
    answer_text(monkeypatch, "X", accepted=False)
    lab.add_zone()
    assert lab.document.project.zones == ()


def test_a_zone_is_removed_by_name(lab: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    assert not lab.remove_zone_action.isEnabled()
    lab.remove_a_zone()
    assert "no zone to remove" in lab.statusBar().currentMessage()
    lab.canvas.select_ids({"nas"})
    answer_text(monkeypatch, "LAN")
    lab.add_zone()
    assert lab.remove_zone_action.isEnabled()
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: ("LAN", True)))
    lab.remove_zone_action.trigger()
    assert lab.document.project.zones == ()
    assert lab.document.undo_label == "Remove zone"


def test_cancelling_the_zone_choice_removes_nothing(
    lab: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    lab.canvas.select_ids({"nas"})
    answer_text(monkeypatch, "LAN")
    lab.add_zone()
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: ("", False)))
    lab.remove_a_zone()
    assert len(lab.document.project.zones) == 1


def test_zones_cannot_be_added_from_inside_a_host(
    lab: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = add_node(lab.document.project, "vm", 0, 0, parent="nas")
    lab.document.apply(project, "Add VM")
    lab.canvas.enter("nas")
    lab.canvas.select_ids({"virtual-machine"})
    assert not lab.add_zone_action.isEnabled()


def test_the_homelab_is_renamed_from_the_menu(
    lab: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    answer_text(monkeypatch, "Garage")
    lab.rename_project_action.trigger()
    assert lab.document.project.name == "Garage"
    assert lab.trail_label.text() == "Garage"
    answer_text(monkeypatch, "  ")
    lab.rename_homelab()
    assert "must not be empty" in lab.statusBar().currentMessage()
    answer_text(monkeypatch, "Other", accepted=False)
    lab.rename_homelab()
    assert lab.document.project.name == "Garage"
