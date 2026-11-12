"""The canvas: the grid, the devices on it, and the gestures that edit them.

Every edit goes through ``operations`` and ``Document``, so the canvas decides nothing about
the homelab. It turns a gesture (a drop, a drag, a key) into a call, and redraws from the
document when that changes.
"""

import math
from typing import Any

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QInputDialog,
    QLineEdit,
    QStyleOptionGraphicsItem,
    QWidget,
)

from homelab_maker.catalog import CATALOG
from homelab_maker.document import Document
from homelab_maker.grid import CELL, cell_at, cell_origin, clamp_zoom, snap
from homelab_maker.gui.icons import paint_kind
from homelab_maker.gui.palette import MIME_KIND
from homelab_maker.gui.theme import Tokens
from homelab_maker.model import Medium, Project
from homelab_maker.operations import add_node, can_move, delete_nodes, move_nodes, rename_node
from homelab_maker.viewmodel import drawn_links, inside_count

# The card is a little smaller than its cell, so neighbours never touch.
CARD = 96
MARGIN = (CELL - CARD) / 2

# The area that is always reachable, in cells, even when the project is empty.
_MIN_CELLS = QRectF(-8, -6, 32, 22)
_PADDING_CELLS = 6

_LINK_STYLES = {
    Medium.ETHERNET: (2.0, Qt.PenStyle.SolidLine),
    Medium.FIBER: (3.5, Qt.PenStyle.SolidLine),
    Medium.WIFI: (2.0, Qt.PenStyle.DotLine),
    Medium.VPN: (2.0, Qt.PenStyle.DashDotLine),
}


class NodeItem(QGraphicsItem):
    """One device, drawn as a card on its cell."""

    def __init__(self, node_id: str, canvas: "Canvas") -> None:
        super().__init__()
        self.node_id = node_id
        self.kind = ""
        self.name = ""
        self.inside = 0
        self._canvas = canvas
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(1)

    def boundingRect(self) -> QRectF:
        return QRectF(MARGIN - 3, MARGIN - 3, CARD + 6, CARD + 6)

    def center(self) -> QPointF:
        return self.pos() + QPointF(CELL / 2, CELL / 2)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        tokens = self._canvas.tokens
        card = QRectF(MARGIN, MARGIN, CARD, CARD)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = self.isSelected()
        painter.setPen(
            QPen(QColor(tokens.accent if selected else tokens.card_border), 2.5 if selected else 1)
        )
        painter.setBrush(QColor(tokens.card))
        painter.drawRoundedRect(card, 10, 10)

        paint_kind(
            painter,
            self.kind,
            QRectF(card.center().x() - 20, card.top() + 9, 40, 40),
            QColor(tokens.text),
        )

        font = painter.font()
        font.setPointSizeF(9)
        painter.setFont(font)
        label = painter.fontMetrics().elidedText(self.name, Qt.TextElideMode.ElideRight, CARD - 12)
        painter.setPen(QColor(tokens.text))
        painter.drawText(
            QRectF(card.left() + 6, card.top() + 52, CARD - 12, 20),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            label,
        )
        if self.inside:
            font.setPointSizeF(8)
            painter.setFont(font)
            painter.setPen(QColor(tokens.text_muted))
            painter.drawText(
                QRectF(card.left() + 6, card.top() + 71, CARD - 12, 18),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                f"{self.inside} inside",
            )

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            x, y = snap(value.x(), value.y())
            return QPointF(x, y)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._canvas.node_moved()
        return super().itemChange(change, value)


class Backdrop(QGraphicsItem):
    """The zones and the links, drawn behind the cards."""

    def __init__(self, canvas: "Canvas") -> None:
        super().__init__()
        self._canvas = canvas
        self._extent = QRectF()
        self.setZValue(-1)

    def set_extent(self, rect: QRectF) -> None:
        if rect != self._extent:
            self.prepareGeometryChange()
            self._extent = rect

    def boundingRect(self) -> QRectF:
        return self._extent

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        canvas = self._canvas
        tokens = canvas.tokens
        project = canvas.document.project
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for index, zone in enumerate(project.zones):
            x, y = cell_origin(zone.x, zone.y)
            rect = QRectF(x, y, zone.width * CELL, zone.height * CELL)
            colour = QColor(tokens.zones[index % len(tokens.zones)])
            fill = QColor(colour)
            fill.setAlpha(tokens.zone_alpha)
            painter.setPen(QPen(colour, 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 12, 12)
            painter.setPen(QColor(tokens.text_muted))
            painter.drawText(
                rect.adjusted(10, 6, -10, -6),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                zone.name,
            )

        for link in drawn_links(project):
            a, b = canvas.node_items.get(link.a), canvas.node_items.get(link.b)
            if a is None or b is None:
                continue
            width, style = _LINK_STYLES[link.medium]
            painter.setPen(QPen(QColor(tokens.link), width, style, Qt.PenCapStyle.RoundCap))
            painter.drawLine(a.center(), b.center())


class Canvas(QGraphicsView):
    status_message = Signal(str)
    selection_changed = Signal()

    def __init__(self, document: Document, tokens: Tokens, parent: QWidget | None = None) -> None:
        scene = QGraphicsScene()
        super().__init__(scene, parent)
        # The view does not own its scene, so without a parent it would be deleted at once.
        scene.setParent(self)
        self.setObjectName("canvas")
        self.document = document
        self.tokens = tokens
        self.node_items: dict[str, NodeItem] = {}
        self._zoom = 1.0
        self._panning = False

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)

        self._backdrop = Backdrop(self)
        scene.addItem(self._backdrop)
        scene.selectionChanged.connect(self.selection_changed)
        document.subscribe(self.refresh)
        self.refresh()

    # ----------------------------------------------------------------------- drawing

    def set_tokens(self, tokens: Tokens) -> None:
        self.tokens = tokens
        self.scene().update()
        self.viewport().update()

    def drawBackground(self, painter: QPainter, area: QRectF | QRect) -> None:
        rect = QRectF(area)
        tokens = self.tokens
        painter.fillRect(rect, QColor(tokens.background))
        first_x, first_y = math.floor(rect.left() / CELL), math.floor(rect.top() / CELL)
        last_x, last_y = math.ceil(rect.right() / CELL), math.ceil(rect.bottom() / CELL)
        if (last_x - first_x) * (last_y - first_y) > 40_000:
            return  # zoomed so far out that the lines would be a blur anyway
        minor, major = QPen(QColor(tokens.grid_minor), 0), QPen(QColor(tokens.grid_major), 0)
        for column in range(first_x, last_x + 1):
            painter.setPen(major if column % 5 == 0 else minor)
            painter.drawLine(
                QPointF(column * CELL, rect.top()), QPointF(column * CELL, rect.bottom())
            )
        for row in range(first_y, last_y + 1):
            painter.setPen(major if row % 5 == 0 else minor)
            painter.drawLine(QPointF(rect.left(), row * CELL), QPointF(rect.right(), row * CELL))

    def drawForeground(self, painter: QPainter, area: QRectF | QRect) -> None:
        if self.document.project.nodes:
            return
        painter.setPen(QColor(self.tokens.text_muted))
        font = painter.font()
        font.setPointSizeF(12)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, 0, 8 * CELL, 3 * CELL),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            "Double-click a device in the list, or drag one here.",
        )

    def node_moved(self) -> None:
        """A card moved, so the links that end on it have to follow."""
        self._backdrop.update()

    # ---------------------------------------------------------------------- the model

    def refresh(self) -> None:
        """Make the scene match the document, keeping the items (and the selection) alive."""
        project = self.document.project
        scene = self.scene()
        roots = {node.id: node for node in project.children(None)}

        for node_id in [i for i in self.node_items if i not in roots]:
            scene.removeItem(self.node_items.pop(node_id))
        for node in roots.values():
            item = self.node_items.get(node.id)
            if item is None:
                item = NodeItem(node.id, self)
                self.node_items[node.id] = item
                scene.addItem(item)
            item.kind, item.name = node.kind, node.name
            item.inside = inside_count(project, node.id)
            x, y = cell_origin(node.x, node.y)
            if item.pos() != QPointF(x, y):
                item.setPos(x, y)
            item.update()

        self._update_extent(project)
        self._backdrop.update()
        self.viewport().update()

    def _update_extent(self, project: Project) -> None:
        cells = QRectF(_MIN_CELLS)
        for node in project.children(None):
            cells = cells.united(QRectF(node.x, node.y, 1, 1))
        for zone in project.zones:
            cells = cells.united(QRectF(zone.x, zone.y, zone.width, zone.height))
        cells.adjust(-_PADDING_CELLS, -_PADDING_CELLS, _PADDING_CELLS, _PADDING_CELLS)
        rect = QRectF(
            cells.x() * CELL, cells.y() * CELL, cells.width() * CELL, cells.height() * CELL
        )
        self.scene().setSceneRect(rect)
        self._backdrop.set_extent(rect)

    # ---------------------------------------------------------------------- selection

    def selected_ids(self) -> list[str]:
        return sorted(item.node_id for item in self.node_items.values() if item.isSelected())

    def select_ids(self, node_ids: set[str]) -> None:
        self.scene().clearSelection()
        for node_id in node_ids:
            item = self.node_items.get(node_id)
            if item is not None:
                item.setSelected(True)

    def select_all(self) -> None:
        for item in self.node_items.values():
            item.setSelected(True)

    # ----------------------------------------------------------------------- editing

    def add_device(self, kind_key: str, cell_x: int, cell_y: int) -> None:
        try:
            project, new_id = add_node(self.document.project, kind_key, cell_x, cell_y)
        except ValueError as exc:
            self.status_message.emit(str(exc))
            return
        self.document.apply(project, f"Add {CATALOG[kind_key].label.lower()}")
        self.select_ids({new_id})

    def add_at_center(self, kind_key: str) -> None:
        centre = self.mapToScene(self.viewport().rect().center())
        self.add_device(kind_key, *cell_at(centre.x(), centre.y()))

    def delete_selected(self) -> None:
        ids = self.selected_ids()
        if ids:
            label = "Delete device" if len(ids) == 1 else "Delete devices"
            self.document.apply(delete_nodes(self.document.project, ids), label)

    def rename_selected(self) -> None:
        ids = self.selected_ids()
        if len(ids) != 1:
            return
        node = self.document.project.node(ids[0])
        if node is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename device", "Name:", QLineEdit.EchoMode.Normal, node.name
        )
        if not accepted:
            return
        try:
            self.document.apply(rename_node(self.document.project, node.id, name), "Rename device")
        except ValueError as exc:
            self.status_message.emit(str(exc))

    def nudge(self, dx: int, dy: int) -> None:
        """Move the selection by whole cells (the arrow keys)."""
        ids = self.selected_ids()
        if not ids:
            return
        project = self.document.project
        if can_move(project, ids, dx, dy):
            label = "Move device" if len(ids) == 1 else "Move devices"
            self.document.apply(move_nodes(project, ids, dx, dy), label)
        else:
            self.status_message.emit("That cell is taken.")

    def _commit_drag(self) -> None:
        """After a drag, turn how far the cards moved into one undoable step."""
        ids = self.selected_ids()
        project = self.document.project
        first = project.node(ids[0]) if ids else None
        item = self.node_items.get(ids[0]) if ids else None
        if first is None or item is None:
            return
        cell_x, cell_y = cell_at(item.pos().x() + 1, item.pos().y() + 1)
        dx, dy = cell_x - first.x, cell_y - first.y
        if dx == 0 and dy == 0:
            return
        if can_move(project, ids, dx, dy):
            label = "Move device" if len(ids) == 1 else "Move devices"
            self.document.apply(move_nodes(project, ids, dx, dy), label)
        else:
            self.refresh()  # the cards snap back to where the document says they are
            self.status_message.emit("That cell is taken.")

    # ---------------------------------------------------------------------- the view

    @property
    def zoom(self) -> float:
        return self._zoom

    def zoom_by(self, factor: float) -> None:
        target = clamp_zoom(self._zoom, factor)
        applied = target / self._zoom
        self._zoom = target
        self.scale(applied, applied)

    def zoom_reset(self) -> None:
        self.resetTransform()
        self._zoom = 1.0

    def zoom_fit(self) -> None:
        if not self.node_items:
            self.zoom_reset()
            return
        bounds = QRectF()
        for item in self.node_items.values():
            bounds = bounds.united(item.mapRectToScene(item.boundingRect()))
        self.fitInView(
            bounds.adjusted(-CELL, -CELL, CELL, CELL), Qt.AspectRatioMode.KeepAspectRatio
        )
        self._zoom = clamp_zoom(self.transform().m11(), 1.0)
        if self._zoom != self.transform().m11():
            self.resetTransform()
            self.scale(self._zoom, self._zoom)

    # --------------------------------------------------------------------- the events

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key, modifiers = Qt.Key(event.key()), event.modifiers()
        arrows = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
        elif key == Qt.Key.Key_F2:
            self.rename_selected()
        elif key == Qt.Key.Key_A and modifiers & Qt.KeyboardModifier.ControlModifier:
            self.select_all()
        elif key in arrows and not modifiers & Qt.KeyboardModifier.ControlModifier:
            self.nudge(*arrows[key])
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, NodeItem) and event.button() == Qt.MouseButton.LeftButton:
            self.select_ids({item.node_id})
            self.rename_selected()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _as_left_button(self, event: QMouseEvent) -> QMouseEvent:
        # Dragging with the middle button pans: the view's hand tool only listens to the left.
        pressed = (
            Qt.MouseButton.LeftButton
            if event.type() != QMouseEvent.Type.MouseButtonRelease
            else Qt.MouseButton.NoButton
        )
        return QMouseEvent(
            event.type(),
            event.position(),
            event.globalPosition(),
            Qt.MouseButton.LeftButton,
            pressed,
            event.modifiers(),
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            super().mousePressEvent(self._as_left_button(event))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            super().mouseMoveEvent(self._as_left_button(event))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning and event.button() == Qt.MouseButton.MiddleButton:
            super().mouseReleaseEvent(self._as_left_button(event))
            self._panning = False
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._commit_drag()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
            return
        super().wheelEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(MIME_KIND):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasFormat(MIME_KIND):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if not event.mimeData().hasFormat(MIME_KIND):
            super().dropEvent(event)
            return
        key = bytes(event.mimeData().data(MIME_KIND).data()).decode("utf-8", errors="replace")
        spot = self.mapToScene(event.position().toPoint())
        self.add_device(key, *cell_at(spot.x(), spot.y()))
        event.acceptProposedAction()
