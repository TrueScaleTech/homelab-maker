"""Gestures for the window tests: real mouse and wheel events sent to the canvas."""

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from homelab_maker.grid import CELL, cell_origin
from homelab_maker.gui.canvas import Canvas


def cell_point(canvas: Canvas, x: int, y: int) -> QPoint:
    """Where, in the canvas viewport, the centre of a grid cell is on screen."""
    px, py = cell_origin(x, y)
    return canvas.mapFromScene(QPointF(px + CELL / 2, py + CELL / 2))


def _send(
    canvas: Canvas,
    kind: QEvent.Type,
    pos: QPoint,
    button: Qt.MouseButton,
    buttons: Qt.MouseButton,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    viewport = canvas.viewport()
    event = QMouseEvent(
        kind, QPointF(pos), QPointF(viewport.mapToGlobal(pos)), button, buttons, modifiers
    )
    QApplication.sendEvent(viewport, event)


def press(
    canvas: Canvas,
    pos: QPoint,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    _send(canvas, QEvent.Type.MouseButtonPress, pos, button, button, modifiers)


def move(
    canvas: Canvas,
    pos: QPoint,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    _send(canvas, QEvent.Type.MouseMove, pos, Qt.MouseButton.NoButton, button, modifiers)


def release(
    canvas: Canvas,
    pos: QPoint,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    _send(canvas, QEvent.Type.MouseButtonRelease, pos, button, Qt.MouseButton.NoButton, modifiers)


def drag(
    canvas: Canvas,
    start: QPoint,
    end: QPoint,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    steps: int = 6,
) -> None:
    """Press at ``start``, move in small steps like a hand does, release at ``end``."""
    press(canvas, start, button, modifiers)
    for step in range(1, steps + 1):
        point = QPoint(
            start.x() + (end.x() - start.x()) * step // steps,
            start.y() + (end.y() - start.y()) * step // steps,
        )
        move(canvas, point, button, modifiers)
    release(canvas, end, button, modifiers)


def click(canvas: Canvas, pos: QPoint) -> None:
    press(canvas, pos)
    release(canvas, pos)


def ctrl_wheel(canvas: Canvas, pos: QPoint, delta: int) -> None:
    viewport = canvas.viewport()
    event = QWheelEvent(
        QPointF(pos),
        QPointF(viewport.mapToGlobal(pos)),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(viewport, event)
