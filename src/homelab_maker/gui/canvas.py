"""The canvas: the grid, the devices on it, and the gestures that edit them.

Every edit goes through ``operations`` and ``Document``, so the canvas decides nothing about
the homelab. It turns a gesture (a drop, a drag, a key) into a call, and redraws from the
document when that changes.
"""

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QLineF, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QInputDialog,
    QLineEdit,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from homelab_maker.catalog import CATALOG
from homelab_maker.document import Document
from homelab_maker.grid import CELL, cell_at, cell_origin, clamp_zoom, point_along, snap
from homelab_maker.gui.icons import paint_kind
from homelab_maker.gui.palette import MIME_KIND
from homelab_maker.gui.theme import Tokens
from homelab_maker.model import Medium, Project
from homelab_maker.operations import (
    add_node,
    can_contain,
    can_move,
    connect,
    delete_nodes,
    disconnect,
    move_into,
    move_nodes,
    move_out,
    rename_node,
)
from homelab_maker.viewmodel import drawn_links, inside_count, path_cards, shown_as

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
        # Drawn faded and crossed out while "what goes down" is showing.
        self.offline = False
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
        if self.offline:
            painter.setOpacity(0.4)
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
        if self.offline:
            painter.setOpacity(1.0)
            painter.setPen(
                QPen(QColor(tokens.danger), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.drawLine(card.topLeft() + QPointF(8, 8), card.bottomRight() - QPointF(8, 8))
            painter.drawLine(card.topRight() + QPointF(-8, 8), card.bottomLeft() + QPointF(8, -8))

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

        for index, zone in enumerate(project.zones if canvas.view is None else ()):
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

        for link in drawn_links(project, canvas.view):
            a, b = canvas.node_items.get(link.a), canvas.node_items.get(link.b)
            if a is None or b is None:
                continue
            width, style = _LINK_STYLES[link.medium]
            chosen = link.id == canvas.selected_link
            colour = QColor(tokens.accent if chosen else tokens.link)
            painter.setPen(
                QPen(colour, width + 2 if chosen else width, style, Qt.PenCapStyle.RoundCap)
            )
            painter.drawLine(a.center(), b.center())

        canvas.paint_flow(painter)

        pending = canvas.pending_cable()
        if pending is not None:
            start, end = pending
            painter.setPen(
                QPen(QColor(tokens.accent), 2, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap)
            )
            painter.drawLine(start, end)


class Canvas(QGraphicsView):
    status_message = Signal(str)
    selection_changed = Signal()
    # The canvas now shows the inside of another host, or came back out.
    view_changed = Signal()
    # The cable tool was switched on or off.
    tool_changed = Signal()

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
        # None shows the canvas; a node id shows the inside of that host.
        self.view: str | None = None
        self.selected_link: str | None = None
        self.cable_medium = Medium.ETHERNET
        self._cable_tool = False
        self._cable_from: str | None = None
        self._cable_press: str | None = None
        self._cable_cursor: QPointF | None = None
        # A flow being shown: the devices on its path, whether it gets through, where it stops.
        self._flow: tuple[tuple[str, ...], bool, str | None] | None = None
        self._packet = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.advance_packet)
        # Devices drawn as switched off ("what goes down").
        self.offline: frozenset[str] = frozenset()

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.viewport().setMouseTracking(True)

        self._backdrop = Backdrop(self)
        scene.addItem(self._backdrop)
        scene.selectionChanged.connect(self._scene_selection_changed)
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
        if self.node_items:
            return
        painter.setPen(QColor(self.tokens.text_muted))
        font = painter.font()
        font.setPointSizeF(12)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, 0, 8 * CELL, 3 * CELL),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            "Double-click a device in the list, or drag one here."
            if self.view is None
            else "This host is empty. Add a virtual machine or a container from the list.",
        )

    def node_moved(self) -> None:
        """A card moved, so the links that end on it have to follow."""
        self._backdrop.update()

    # ---------------------------------------------------------------------- the model

    def refresh(self) -> None:
        """Make the scene match the document, keeping the items (and the selection) alive."""
        project = self.document.project
        scene = self.scene()
        if self.view is not None and project.node(self.view) is None:
            self.view = None  # the host was deleted, or an undo took it away
            self.view_changed.emit()
        if self.selected_link is not None and all(
            link.id != self.selected_link for link in project.links
        ):
            self.selected_link = None
        if self._cable_from is not None and project.node(self._cable_from) is None:
            self._cable_from = None
        roots = {node.id: node for node in project.children(self.view)}

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
            item.offline = node.id in self.offline
            x, y = cell_origin(node.x, node.y)
            if item.pos() != QPointF(x, y):
                item.setPos(x, y)
            item.update()

        self._update_extent(project)
        self._backdrop.update()
        self.viewport().update()

    def _update_extent(self, project: Project) -> None:
        cells = QRectF(_MIN_CELLS)
        for node in project.children(self.view):
            cells = cells.united(QRectF(node.x, node.y, 1, 1))
        for zone in project.zones if self.view is None else ():
            cells = cells.united(QRectF(zone.x, zone.y, zone.width, zone.height))
        cells.adjust(-_PADDING_CELLS, -_PADDING_CELLS, _PADDING_CELLS, _PADDING_CELLS)
        rect = QRectF(
            cells.x() * CELL, cells.y() * CELL, cells.width() * CELL, cells.height() * CELL
        )
        self.scene().setSceneRect(rect)
        self._backdrop.set_extent(rect)

    # ---------------------------------------------------------------------- selection

    def _scene_selection_changed(self) -> None:
        if self.selected_link is not None and self.scene().selectedItems():
            self.selected_link = None
            self._backdrop.update()
        self.selection_changed.emit()

    def select_link(self, link_id: str | None) -> None:
        """Select a cable (or nothing). A cable and a device are never selected together."""
        if link_id is not None:
            self.scene().clearSelection()
        if link_id != self.selected_link:
            self.selected_link = link_id
            self._backdrop.update()
            self.selection_changed.emit()

    def link_at(self, scene_pos: QPointF) -> str | None:
        """The id of the cable drawn under a point of the scene, if any."""
        reach = 7 / self._zoom
        best: tuple[float, str] | None = None
        for link in drawn_links(self.document.project, self.view):
            a, b = self.node_items.get(link.a), self.node_items.get(link.b)
            if a is None or b is None:
                continue
            distance = _distance_to_segment(scene_pos, a.center(), b.center())
            if distance <= reach and (best is None or distance < best[0]):
                best = (distance, link.id)
        return best[1] if best else None

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
            project, new_id = add_node(
                self.document.project, kind_key, cell_x, cell_y, parent=self.view
            )
        except ValueError as exc:
            self.status_message.emit(str(exc))
            return
        self.document.apply(project, f"Add {CATALOG[kind_key].label.lower()}")
        self.select_ids({new_id})

    def add_device_inside(self, host_id: str, kind_key: str) -> None:
        """Add a device straight into a host, without opening it first."""
        try:
            project, new_id = add_node(self.document.project, kind_key, 0, 0, parent=host_id)
        except ValueError as exc:
            self.status_message.emit(str(exc))
            return
        host = self.document.project.node(host_id)
        self.document.apply(project, f"Add {CATALOG[kind_key].label.lower()}")
        name = project.node(new_id)
        if host is not None and name is not None:
            self.status_message.emit(f"{name.name} is now inside {host.name}.")

    def add_at_center(self, kind_key: str) -> None:
        centre = self.mapToScene(self.viewport().rect().center())
        self.add_device(kind_key, *cell_at(centre.x(), centre.y()))

    def delete_selected(self) -> None:
        ids = self.selected_ids()
        if not ids and self.selected_link is not None:
            try:
                project = disconnect(self.document.project, [self.selected_link])
            except ValueError as exc:
                self.status_message.emit(str(exc))
                return
            self.document.apply(project, "Remove cable")
            return
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

    def _show_all(self) -> None:
        if self.node_items:
            self.zoom_fit()
        else:
            self.zoom_reset()

    def can_enter(self, node_id: str) -> bool:
        node = self.document.project.node(node_id)
        kind = CATALOG.get(node.kind) if node else None
        return bool(kind and kind.contains)

    def enter(self, node_id: str) -> None:
        """Show the inside of a host."""
        if not self.can_enter(node_id):
            self.status_message.emit("Nothing can be put inside that.")
            return
        self.view = node_id
        self.scene().clearSelection()
        self.selected_link = None
        self._cancel_cable()
        self.refresh()
        self._show_all()
        self.view_changed.emit()
        self.selection_changed.emit()

    def go_to(self, view: str | None) -> None:
        """Show the canvas (``None``) or the inside of any host, selecting the one left."""
        if view == self.view:
            return
        left = self.view
        self.view = view
        self.scene().clearSelection()
        self.selected_link = None
        self._cancel_cable()
        self.refresh()
        self._show_all()
        if left in self.node_items:
            self.select_ids({left})
        self.view_changed.emit()
        self.selection_changed.emit()

    def reveal(self, node_id: str) -> None:
        """Show a device wherever it is, going into its host if need be, and select it."""
        node = self.document.project.node(node_id)
        if node is None:
            return
        self.go_to(node.parent)
        self.select_ids({node_id})

    def leave(self) -> None:
        """Go up one level."""
        if self.view is None:
            return
        host = self.document.project.node(self.view)
        self.go_to(host.parent if host is not None else None)

    def take_out(self) -> None:
        """Move the selected devices out of their host."""
        ids = self.selected_ids()
        if not ids or self.view is None:
            return
        try:
            project = move_out(self.document.project, ids)
        except ValueError as exc:
            self.status_message.emit(str(exc))
            return
        self.document.apply(project, "Take out of host")

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

    def _nest_target(self, pos: QPoint, ids: list[str]) -> str | None:
        """The host card under the pointer that can take every dragged card, if there is one."""
        project = self.document.project
        for item in self.items(pos):
            if isinstance(item, NodeItem) and item.node_id not in ids:
                kinds = [n.kind for n in project.nodes if n.id in ids]
                if kinds and all(can_contain(project, item.node_id, kind) for kind in kinds):
                    return item.node_id
                return None
        return None

    def _commit_drag(self, pos: QPoint | None = None) -> None:
        """After a drag, turn how far the cards moved into one undoable step."""
        ids = self.selected_ids()
        project = self.document.project
        host = self._nest_target(pos, ids) if pos is not None and ids else None
        if host is not None and any(
            (node := project.node(i)) is not None and node.parent != host for i in ids
        ):
            target = project.node(host)
            try:
                nested = move_into(project, ids, host)
            except ValueError as exc:
                self.refresh()
                self.status_message.emit(str(exc))
                return
            self.document.apply(nested, "Put device inside host")
            if target is not None:
                self.status_message.emit(f"Now inside {target.name}.")
            return
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

    # ------------------------------------------------------------------- flows and outages

    def show_flow(self, path: tuple[str, ...], ok: bool, stopped: str | None = None) -> None:
        """Draw a path over the cards: green when the flow gets through, red when it does not."""
        self._flow = (path, ok, stopped)
        self._packet = 0.0
        self._backdrop.update()

    def clear_flow(self) -> None:
        self._flow = None
        self.play_packet(False)
        self._backdrop.update()

    @property
    def flow_shown(self) -> bool:
        return self._flow is not None

    def flow_points(self) -> list[QPointF]:
        """The centres of the cards the shown path passes through, in this view."""
        if self._flow is None:
            return []
        cards = path_cards(self.document.project, self.view, self._flow[0])
        return [self.node_items[c].center() for c in cards if c in self.node_items]

    def play_packet(self, on: bool) -> None:
        """Send a dot along the shown path, over and over, or stop it."""
        if on and self._flow is not None:
            self._timer.start()
        else:
            self._timer.stop()
        self._backdrop.update()

    @property
    def packet_playing(self) -> bool:
        return self._timer.isActive()

    def advance_packet(self, step: float = 0.02) -> None:
        self._packet = (self._packet + step) % 1.0
        self._backdrop.update()

    def packet_position(self) -> QPointF | None:
        points = self.flow_points()
        if not points or not self._timer.isActive():
            return None
        x, y = point_along([(p.x(), p.y()) for p in points], self._packet)
        return QPointF(x, y)

    def paint_flow(self, painter: QPainter) -> None:
        if self._flow is None:
            return
        _, ok, stopped = self._flow
        tokens = self.tokens
        colour = QColor(tokens.ok if ok else tokens.danger)
        points = self.flow_points()
        if len(points) > 1:
            glow = QColor(colour)
            glow.setAlpha(90)
            painter.setPen(
                QPen(
                    glow,
                    9,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPolyline(points)
            painter.setPen(
                QPen(
                    colour,
                    3,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPolyline(points)
        where = self.stop_point(stopped)
        if where is not None:
            painter.setPen(QPen(QColor(tokens.danger), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(where, 30, 30)
            painter.drawLine(where + QPointF(-12, -12), where + QPointF(12, 12))
            painter.drawLine(where + QPointF(12, -12), where + QPointF(-12, 12))
        packet = self.packet_position()
        if packet is not None:
            painter.setPen(QPen(QColor(tokens.card), 2))
            painter.setBrush(colour)
            painter.drawEllipse(packet, 7, 7)

    def stop_point(self, stopped: str | None) -> QPointF | None:
        """Where a blocked flow stops: on a device's card, or in the middle of a cable."""
        if stopped is None:
            return None
        project = self.document.project
        link = next((item for item in project.links if item.id == stopped), None)
        if link is not None:
            a = self.node_items.get(shown_as(project, link.a.node, self.view) or "")
            b = self.node_items.get(shown_as(project, link.b.node, self.view) or "")
            return (a.center() + b.center()) / 2 if a and b else None
        card = shown_as(project, stopped, self.view)
        item = self.node_items.get(card) if card else None
        return item.center() if item else None

    def set_offline(self, node_ids: frozenset[str]) -> None:
        """Draw these devices as switched off. An empty set puts everything back."""
        self.offline = node_ids
        self.refresh()

    # ------------------------------------------------------------------------ cables

    @property
    def cable_tool(self) -> bool:
        return self._cable_tool

    def set_cable_tool(self, on: bool, medium: Medium | None = None) -> None:
        """Switch the cable tool on or off. With it on, dragging from one card to another
        (or clicking one and then the other) joins them instead of moving the card."""
        if medium is not None:
            self.cable_medium = medium
        changed = on != self._cable_tool
        self._cable_tool = on
        self._cancel_cable()
        self.viewport().setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor)
        if changed:
            self.tool_changed.emit()

    def start_cable_from(self, node_id: str) -> None:
        """Switch the tool on with one end already chosen (the context menu does this)."""
        self.set_cable_tool(True)
        self._cable_from = node_id
        self.status_message.emit("Click the device to join it to. Escape cancels.")
        self._backdrop.update()

    def _cancel_cable(self) -> None:
        self._cable_from = None
        self._cable_press = None
        self._cable_cursor = None
        self._backdrop.update()

    def pending_cable(self) -> tuple[QPointF, QPointF] | None:
        """The rubber line of a cable being drawn: from its first card to the pointer."""
        start = self._cable_press or self._cable_from
        item = self.node_items.get(start) if start else None
        if item is None or self._cable_cursor is None:
            return None
        return item.center(), self._cable_cursor

    def _card_at(self, pos: QPoint) -> NodeItem | None:
        for item in self.items(pos):
            if isinstance(item, NodeItem):
                return item
        return None

    def join(self, first: str, second: str) -> None:
        before = self.document.project
        try:
            project, link_id = connect(before, first, second, self.cable_medium)
        except ValueError as exc:
            self.status_message.emit(str(exc))
            return
        names = [node.name for node in map(before.node, (first, second)) if node is not None]
        self.document.apply(project, "Add cable")
        # The new cable is the one to look at, so it is selected.
        self.select_link(link_id)
        self.status_message.emit(f"Joined {' and '.join(names)}.")

    def _cable_press_event(self, event: QMouseEvent) -> None:
        card = self._card_at(event.position().toPoint())
        self._cable_press = card.node_id if card else None
        self._cable_cursor = self.mapToScene(event.position().toPoint())

    def _cable_release_event(self, event: QMouseEvent) -> None:
        card = self._card_at(event.position().toPoint())
        pressed, pending = self._cable_press, self._cable_from
        self._cable_press = None
        self._cable_cursor = None
        if card is None:
            # A click on the empty grid gives up the half-drawn cable.
            self._cable_from = None
            self._backdrop.update()
            return
        if pending is not None and pending != card.node_id:
            self._cable_from = None
            self.join(pending, card.node_id)
        elif pressed is not None and pressed != card.node_id:
            self._cable_from = None
            self.join(pressed, card.node_id)
        elif pressed == card.node_id and pending != card.node_id:
            self._cable_from = card.node_id
            self.status_message.emit("Click the device to join it to. Escape cancels.")
        else:
            self._cable_from = None
        self._backdrop.update()

    # ----------------------------------------------------------------- context menu

    def node_menu(self, node_id: str) -> QMenu:
        """The menu of a device, built but not shown, so it can be tested."""
        project = self.document.project
        node = project.node(node_id)
        menu = QMenu(self)
        if node is None:
            return menu
        kind = CATALOG.get(node.kind)
        if kind and kind.contains:
            menu.addAction("Open inside", lambda: self.enter(node_id)).setObjectName("open")
            inside = menu.addMenu("Add inside")
            inside.setObjectName("add-inside")
            for key in sorted(kind.contains):
                inside.addAction(
                    CATALOG[key].label,
                    lambda key=key: self.add_device_inside(node_id, key),  # type: ignore[misc]
                )
        menu.addAction("Cable from here…", lambda: self.start_cable_from(node_id)).setObjectName(
            "cable"
        )
        menu.addSeparator()
        menu.addAction("Rename…", lambda: self._act_on(node_id, self.rename_selected))
        if node.parent is not None:
            menu.addAction(
                "Take out of its host", lambda: self._act_on(node_id, self.take_out)
            ).setObjectName("take-out")
        menu.addAction("Delete", lambda: self._act_on(node_id, self.delete_selected)).setObjectName(
            "delete"
        )
        return menu

    def _act_on(self, node_id: str, action: Callable[[], None]) -> None:
        self.select_ids({node_id})
        action()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        card = self._card_at(event.pos())
        if card is None:
            super().contextMenuEvent(event)
            return
        if not card.isSelected():
            self.select_ids({card.node_id})
        self.node_menu(card.node_id).exec(event.globalPos())
        event.accept()

    # ------------------------------------------------------------------------ images

    def content_rect(self) -> QRectF:
        """The area the drawing occupies in this view, with some room around it."""
        bounds = QRectF()
        for item in self.node_items.values():
            bounds = bounds.united(item.mapRectToScene(item.boundingRect()))
        for zone in self.document.project.zones if self.view is None else ():
            x, y = cell_origin(zone.x, zone.y)
            bounds = bounds.united(QRectF(x, y, zone.width * CELL, zone.height * CELL))
        if bounds.isEmpty():
            bounds = QRectF(0, 0, 4 * CELL, 3 * CELL)
        return bounds.adjusted(-CELL / 2, -CELL / 2, CELL / 2, CELL / 2)

    def save_image(self, path: Path) -> None:
        """Write what this view shows to a PNG or an SVG file, without the grid.

        Raises ``ValueError`` for any other suffix. The selection is not drawn.
        """
        suffix = path.suffix.lower()
        if suffix not in (".png", ".svg"):
            raise ValueError("an image is saved as .png or .svg")
        source = self.content_rect()
        width, height = round(source.width()), round(source.height())
        chosen = self.selected_ids()
        link = self.selected_link
        self.scene().clearSelection()
        self.selected_link = None
        try:
            if suffix == ".svg":
                generator = QSvgGenerator()
                generator.setFileName(str(path))
                generator.setSize(QSize(width, height))
                generator.setViewBox(QRectF(0, 0, width, height))
                generator.setTitle(self.document.project.name)
                painter = QPainter(generator)
                target = QRectF(0, 0, width, height)
                painter.fillRect(target, QColor(self.tokens.background))
                self.scene().render(painter, target, source)
                painter.end()
            else:
                image = QImage(width * 2, height * 2, QImage.Format.Format_ARGB32)
                image.fill(QColor(self.tokens.background))
                painter = QPainter(image)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                self.scene().render(painter, QRectF(image.rect()), source)
                painter.end()
                if not image.save(str(path)):
                    raise OSError("the image could not be written")
        finally:
            self.select_ids(set(chosen))
            self.selected_link = link
            self._backdrop.update()

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
        for zone in self.document.project.zones if self.view is None else ():
            x, y = cell_origin(zone.x, zone.y)
            bounds = bounds.united(QRectF(x, y, zone.width * CELL, zone.height * CELL))
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
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            ids = self.selected_ids()
            if len(ids) == 1 and self.can_enter(ids[0]):
                self.enter(ids[0])
            else:
                super().keyPressEvent(event)
                return
        elif key == Qt.Key.Key_Escape:
            if self._cable_from is not None or self._cable_press is not None:
                self._cancel_cable()
            elif self._cable_tool:
                self.set_cable_tool(False)
            elif self.selected_link is not None:
                self.select_link(None)
            else:
                self.leave()
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
        if self._cable_tool and event.button() == Qt.MouseButton.LeftButton:
            self._cable_press_event(event)
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            super().mousePressEvent(self._as_left_button(event))
            event.accept()
            return
        super().mousePressEvent(event)
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._card_at(event.position().toPoint()) is None
        ):
            self.select_link(self.link_at(self.mapToScene(event.position().toPoint())))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._cable_tool and (self._cable_press or self._cable_from):
            self._cable_cursor = self.mapToScene(event.position().toPoint())
            self._backdrop.update()
            event.accept()
            return
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
        if self._cable_tool and event.button() == Qt.MouseButton.LeftButton:
            self._cable_release_event(event)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._commit_drag(event.position().toPoint())

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


def _distance_to_segment(point: QPointF, start: QPointF, end: QPointF) -> float:
    line = QLineF(start, end)
    length = line.length()
    if length == 0:
        return QLineF(point, start).length()
    along = (
        (point.x() - start.x()) * (end.x() - start.x())
        + (point.y() - start.y()) * (end.y() - start.y())
    ) / (length * length)
    along = max(0.0, min(1.0, along))
    nearest = QPointF(
        start.x() + along * (end.x() - start.x()), start.y() + along * (end.y() - start.y())
    )
    return QLineF(point, nearest).length()
