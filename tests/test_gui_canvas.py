import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog

from helpers import cell_point, click, ctrl_wheel, drag, move, press, release
from homelab_maker.grid import ZOOM_MAX, ZOOM_MIN, cell_origin
from homelab_maker.gui.canvas import Canvas
from homelab_maker.gui.main_window import MainWindow
from homelab_maker.gui.palette import MIME_KIND
from homelab_maker.model import Project
from homelab_maker.operations import add_node
from homelab_maker.validation import validate


def with_devices(window: MainWindow, *devices: tuple[str, int, int]) -> Canvas:
    """Place devices through the document, as earlier edits, and return the canvas."""
    project = window.document.project
    for kind, x, y in devices:
        project, _ = add_node(project, kind, x, y)
    window.document.apply(project, "Set up")
    QApplication.processEvents()
    return window.canvas


def positions(window: MainWindow) -> dict[str, tuple[int, int]]:
    return {node.id: (node.x, node.y) for node in window.document.project.nodes}


# ------------------------------------------------------------------------ placing


def test_a_blank_canvas_shows_nothing_and_says_how_to_start(window: MainWindow) -> None:
    assert window.canvas.node_items == {}
    window.canvas.grab()  # draws the hint without error


def test_dropping_a_kind_from_the_list_places_it_under_the_pointer(window: MainWindow) -> None:
    canvas = window.canvas
    mime = QMimeData()
    mime.setData(MIME_KIND, b"switch")
    target = cell_point(canvas, 3, 2)
    event = QDropEvent(
        QPointF(target),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.dropEvent(event)
    assert positions(window) == {"switch": (3, 2)}
    assert canvas.selected_ids() == ["switch"]
    assert window.document.undo_label == "Add switch"


def test_a_drop_that_is_not_one_of_ours_is_ignored(window: MainWindow) -> None:
    mime = QMimeData()
    mime.setText("hello")
    event = QDropEvent(
        QPointF(cell_point(window.canvas, 1, 1)),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.canvas.dropEvent(event)
    assert window.document.project == Project()


def test_a_drop_of_an_unknown_kind_says_so_and_changes_nothing(window: MainWindow) -> None:
    heard: list[str] = []
    window.canvas.status_message.connect(heard.append)
    mime = QMimeData()
    mime.setData(MIME_KIND, b"toaster")
    event = QDropEvent(
        QPointF(cell_point(window.canvas, 1, 1)),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.canvas.dropEvent(event)
    assert window.document.project == Project()
    assert heard
    assert "unknown device kind" in heard[0]


def test_dropping_on_a_taken_cell_lands_on_a_free_one(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 2, 2))
    canvas.add_device("switch", 2, 2)
    assert validate(window.document.project) == []
    assert len(set(positions(window).values())) == 2


# ------------------------------------------------------------------------ dragging


def test_dragging_a_card_moves_it_by_whole_cells_as_one_undoable_step(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    steps_before = window.document.undo_label
    drag(canvas, cell_point(canvas, 1, 1), cell_point(canvas, 4, 2))
    assert positions(window) == {"nas": (4, 2)}
    assert window.document.undo_label == "Move device"
    window.document.undo()
    assert positions(window) == {"nas": (1, 1)}
    assert window.document.undo_label == steps_before  # exactly one step was added


def test_the_card_sits_on_cell_corners_the_whole_time_it_is_dragged(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    start = cell_point(canvas, 1, 1)
    press(canvas, start)
    for offset in (QPoint(37, 11), QPoint(131, 59), QPoint(203, 143)):
        move(canvas, start + offset)
        position = canvas.node_items["nas"].pos()
        assert position.x() % 112 == 0
        assert position.y() % 112 == 0
    release(canvas, start + QPoint(203, 143))
    assert positions(window) == {"nas": (3, 2)}


def test_a_small_wobble_inside_the_cell_changes_nothing(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    start = cell_point(canvas, 1, 1)
    drag(canvas, start, start + QPoint(10, 8))
    assert positions(window) == {"nas": (1, 1)}
    assert window.document.undo_label == "Set up"


def test_a_card_dropped_on_another_snaps_back_and_says_why(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1), ("switch", 3, 1))
    heard: list[str] = []
    canvas.status_message.connect(heard.append)
    drag(canvas, cell_point(canvas, 1, 1), cell_point(canvas, 3, 1))
    assert positions(window) == {"nas": (1, 1), "switch": (3, 1)}
    assert window.document.undo_label == "Set up"
    assert heard == ["That cell is taken."]
    # The card is drawn back on its own cell, not left where it was let go.
    assert canvas.node_items["nas"].pos().x() == 1 * 112


def test_clicking_a_card_selects_it_and_clicking_empty_space_clears_it(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1), ("switch", 3, 1))
    click(canvas, cell_point(canvas, 1, 1))
    assert canvas.selected_ids() == ["nas"]
    click(canvas, cell_point(canvas, 6, 5))
    assert canvas.selected_ids() == []


def test_a_rubber_band_selects_what_it_covers_and_the_group_moves_as_one_step(
    window: MainWindow,
) -> None:
    canvas = with_devices(window, ("nas", 1, 1), ("switch", 2, 1), ("printer", 6, 4))
    start = cell_point(canvas, 0, 0) + QPoint(-30, -30)
    end = cell_point(canvas, 2, 2)
    drag(canvas, start, end)
    assert canvas.selected_ids() == ["nas", "switch"]

    drag(canvas, cell_point(canvas, 1, 1), cell_point(canvas, 1, 3))
    assert positions(window) == {"nas": (1, 3), "switch": (2, 3), "printer": (6, 4)}
    assert window.document.undo_label == "Move devices"
    window.document.undo()
    assert positions(window)["nas"] == (1, 1)
    assert positions(window)["switch"] == (2, 1)


def test_a_group_dragged_onto_something_snaps_back_whole(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1), ("switch", 2, 1), ("printer", 4, 1))
    canvas.select_ids({"nas", "switch"})
    drag(canvas, cell_point(canvas, 1, 1), cell_point(canvas, 3, 1))
    assert positions(window) == {"nas": (1, 1), "switch": (2, 1), "printer": (4, 1)}


def test_the_links_follow_a_card_while_it_is_dragged(window: MainWindow, sample: Project) -> None:
    window.document.replace(sample, None)
    canvas = window.canvas
    canvas.zoom_fit()
    QApplication.processEvents()
    before = canvas.grab().toImage()
    drag(canvas, cell_point(canvas, 6, 0), cell_point(canvas, 6, -2))
    assert canvas.grab().toImage() != before


# ------------------------------------------------------------------------ the keys


def test_delete_removes_the_selection_and_undo_brings_it_back(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1), ("switch", 3, 1))
    canvas.select_ids({"nas"})
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert positions(window) == {"switch": (3, 1)}
    assert "nas" not in canvas.node_items
    window.document.undo()
    assert set(positions(window)) == {"nas", "switch"}
    assert set(canvas.node_items) == {"nas", "switch"}


def test_delete_with_nothing_selected_does_nothing(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert set(positions(window)) == {"nas"}


def test_the_arrow_keys_move_the_selection_one_cell(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    canvas.select_ids({"nas"})
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    QTest.keyClick(canvas, Qt.Key.Key_Down)
    QTest.keyClick(canvas, Qt.Key.Key_Left)
    QTest.keyClick(canvas, Qt.Key.Key_Up)
    assert positions(window) == {"nas": (1, 1)}
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    assert positions(window) == {"nas": (2, 1)}


def test_an_arrow_key_into_a_neighbour_is_refused_with_a_message(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1), ("switch", 2, 1))
    heard: list[str] = []
    canvas.status_message.connect(heard.append)
    canvas.select_ids({"nas"})
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    assert positions(window) == {"nas": (1, 1), "switch": (2, 1)}
    assert heard == ["That cell is taken."]


def test_control_a_selects_everything(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1), ("switch", 3, 1))
    QTest.keyClick(canvas, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert canvas.selected_ids() == ["nas", "switch"]


def test_an_unrelated_key_is_left_alone(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    canvas.select_ids({"nas"})
    QTest.keyClick(canvas, Qt.Key.Key_X)
    assert positions(window) == {"nas": (1, 1)}


# ----------------------------------------------------------------------- renaming


def answer(monkeypatch: pytest.MonkeyPatch, text: str, accepted: bool = True) -> list[str]:
    asked: list[str] = []

    def fake(
        _parent: object, _title: str, _label: str, _mode: object, current: str
    ) -> tuple[str, bool]:
        asked.append(current)
        return text, accepted

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(fake))
    return asked


def test_double_clicking_a_card_renames_it(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    asked = answer(monkeypatch, "Backup NAS")
    pos = cell_point(canvas, 1, 1)
    press(canvas, pos)
    release(canvas, pos)
    QTest.mouseDClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos
    )
    assert asked == ["NAS"]
    node = window.document.project.node("nas")
    assert node is not None
    assert node.name == "Backup NAS"
    assert window.document.undo_label == "Rename device"


def test_f2_renames_the_one_selected_card(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    answer(monkeypatch, "Archive")
    canvas.select_ids({"nas"})
    QTest.keyClick(canvas, Qt.Key.Key_F2)
    node = window.document.project.node("nas")
    assert node is not None
    assert node.name == "Archive"


def test_cancelling_the_rename_changes_nothing(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    answer(monkeypatch, "Other", accepted=False)
    canvas.select_ids({"nas"})
    QTest.keyClick(canvas, Qt.Key.Key_F2)
    assert window.document.undo_label == "Set up"


def test_an_empty_name_is_refused_with_a_message(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    heard: list[str] = []
    canvas.status_message.connect(heard.append)
    answer(monkeypatch, "   ")
    canvas.select_ids({"nas"})
    QTest.keyClick(canvas, Qt.Key.Key_F2)
    assert window.document.undo_label == "Set up"
    assert heard
    assert "must not be empty" in heard[0]


def test_rename_needs_exactly_one_card(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    canvas = with_devices(window, ("nas", 1, 1), ("switch", 3, 1))
    asked = answer(monkeypatch, "Nope")
    canvas.select_all()
    QTest.keyClick(canvas, Qt.Key.Key_F2)
    canvas.select_ids(set())
    QTest.keyClick(canvas, Qt.Key.Key_F2)
    assert asked == []


def test_double_clicking_empty_space_renames_nothing(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    asked = answer(monkeypatch, "Nope")
    QTest.mouseDClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        cell_point(canvas, 7, 5),
    )
    assert asked == []


# ----------------------------------------------------------------------- the view


def test_control_and_the_wheel_zoom_within_the_limits(window: MainWindow) -> None:
    canvas = window.canvas
    centre = canvas.viewport().rect().center()
    ctrl_wheel(canvas, centre, 120)
    assert canvas.zoom > 1.0
    for _ in range(60):
        ctrl_wheel(canvas, centre, 120)
    assert canvas.zoom == pytest.approx(ZOOM_MAX)
    for _ in range(120):
        ctrl_wheel(canvas, centre, -120)
    assert canvas.zoom == pytest.approx(ZOOM_MIN)
    canvas.zoom_reset()
    assert canvas.zoom == 1.0


def test_the_wheel_alone_scrolls_and_does_not_zoom(window: MainWindow) -> None:
    canvas = window.canvas
    scrollbar = canvas.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum() // 2)
    before = scrollbar.value()
    QTest.mouseMove(canvas.viewport())
    from PySide6.QtGui import QWheelEvent

    event = QWheelEvent(
        QPointF(10, 10),
        QPointF(canvas.viewport().mapToGlobal(QPoint(10, 10))),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(canvas.viewport(), event)
    assert canvas.zoom == 1.0
    assert scrollbar.value() != before


def test_dragging_with_the_middle_button_pans_and_restores_the_selection_tool(
    window: MainWindow,
) -> None:
    canvas = window.canvas
    bar = canvas.horizontalScrollBar()
    bar.setValue(bar.maximum() // 2)
    before = bar.value()
    start = canvas.viewport().rect().center()
    drag(canvas, start, start + QPoint(-150, 0), button=Qt.MouseButton.MiddleButton)
    assert bar.value() != before
    assert canvas.dragMode() == canvas.DragMode.RubberBandDrag
    # And the left button still draws a selection rectangle afterwards.
    with_devices(window, ("nas", 1, 1))
    drag(canvas, cell_point(canvas, 0, 0) + QPoint(-20, -20), cell_point(canvas, 2, 2))
    assert canvas.selected_ids() == ["nas"]


def test_fit_brings_every_card_into_view(window: MainWindow, sample: Project) -> None:
    window.document.replace(sample, None)
    canvas = window.canvas
    canvas.zoom_fit()
    QApplication.processEvents()
    visible = canvas.viewport().rect()
    for item in canvas.node_items.values():
        corner = canvas.mapFromScene(item.pos())
        assert visible.contains(corner), item.node_id
    # The zones are part of the picture too, so none of them is cut off at the edge.
    for zone in sample.zones:
        x, y = cell_origin(zone.x, zone.y)
        far = canvas.mapFromScene(QPointF(x + zone.width * 112, y + zone.height * 112))
        assert visible.contains(far), zone.id
    assert ZOOM_MIN <= canvas.zoom <= ZOOM_MAX


def test_fit_on_an_empty_canvas_goes_back_to_actual_size(window: MainWindow) -> None:
    window.canvas.zoom_by(2.0)
    window.canvas.zoom_fit()
    assert window.canvas.zoom == 1.0


# ------------------------------------------------------------------------- drawing


def test_the_example_is_drawn_as_cards_with_hosted_things_counted(
    window: MainWindow, sample: Project
) -> None:
    window.document.replace(sample, None)
    canvas = window.canvas
    assert len(canvas.node_items) == 9  # nine devices on the canvas, four more inside the NAS
    assert canvas.node_items["nas"].inside == 4
    assert canvas.node_items["switch"].inside == 0


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_example_draws_in_both_themes(window: MainWindow, sample: Project, scheme: str) -> None:
    window.document.replace(sample, None)
    window.set_scheme(scheme)  # type: ignore[arg-type]
    canvas = window.canvas
    canvas.select_ids({"nas"})
    image = canvas.grab().toImage()
    assert image.width() > 0
    # Something other than the background colour was drawn.
    background = image.pixelColor(2, 2)
    assert any(
        image.pixelColor(x, y) != background
        for x in range(0, image.width(), 7)
        for y in range(0, image.height(), 7)
    )


def test_undoing_an_add_removes_the_card(window: MainWindow) -> None:
    canvas = window.canvas
    canvas.add_device("nas", 2, 2)
    assert set(canvas.node_items) == {"nas"}
    window.document.undo()
    assert canvas.node_items == {}
    window.document.redo()
    assert set(canvas.node_items) == {"nas"}


def test_a_card_that_is_moved_by_undo_follows(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    drag(canvas, cell_point(canvas, 1, 1), cell_point(canvas, 3, 3))
    assert canvas.node_items["nas"].pos().x() == 3 * 112
    window.document.undo()
    assert canvas.node_items["nas"].pos().x() == 1 * 112


def test_the_scene_is_always_large_enough_to_reach_every_card(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 50, 40))
    rect = canvas.sceneRect()
    item = canvas.node_items["nas"]
    assert rect.contains(item.mapRectToScene(item.boundingRect()))


def test_press_move_release_helpers_agree_with_a_plain_click(window: MainWindow) -> None:
    canvas = with_devices(window, ("nas", 1, 1))
    pos = cell_point(canvas, 1, 1)
    press(canvas, pos)
    move(canvas, pos + QPoint(2, 2))
    release(canvas, pos + QPoint(2, 2))
    assert canvas.selected_ids() == ["nas"]
    assert positions(window) == {"nas": (1, 1)}
