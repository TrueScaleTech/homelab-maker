"""Every icon the application shows, drawn in code on one 24-unit grid.

No icon comes from a font or an image file, so they stay sharp at every size and take
their colour from the theme. Run ``python -m homelab_maker.gui.icons out.ico`` to write
the application icon that the Windows build needs.
"""

import sys
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

GRID = 24.0


def _box(p: QPainter, x: float, y: float, w: float, h: float, r: float = 2.0) -> None:
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)


def _line(p: QPainter, x1: float, y1: float, x2: float, y2: float) -> None:
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _dot(p: QPainter, x: float, y: float, r: float = 0.9) -> None:
    p.drawEllipse(QPointF(x, y), r, r)


def _poly(p: QPainter, *points: tuple[float, float]) -> None:
    path = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    path.closeSubpath()
    p.drawPath(path)


def _internet(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    p.drawEllipse(QPointF(12, 12), 4, 9)
    _line(p, 3, 12, 21, 12)


def _modem(p: QPainter) -> None:
    _box(p, 3, 11, 18, 8)
    _line(p, 7, 11, 5, 4)
    _line(p, 17, 11, 19, 4)
    _dot(p, 8, 15)
    _dot(p, 12, 15)


def _router(p: QPainter) -> None:
    _box(p, 3, 12, 18, 7)
    _line(p, 7, 12, 7, 5)
    _line(p, 17, 12, 17, 5)
    _dot(p, 8, 15.5)
    _dot(p, 12, 15.5)
    _line(p, 15, 15.5, 18, 15.5)


def _firewall(p: QPainter) -> None:
    path = QPainterPath(QPointF(12, 3))
    path.lineTo(20, 6)
    path.lineTo(20, 12)
    path.cubicTo(20, 17, 16, 20, 12, 21)
    path.cubicTo(8, 20, 4, 17, 4, 12)
    path.lineTo(4, 6)
    path.closeSubpath()
    p.drawPath(path)
    _line(p, 8, 10, 16, 10)
    _line(p, 8, 14, 16, 14)


def _switch(p: QPainter) -> None:
    _box(p, 2, 8, 20, 8)
    for x in (5, 9, 13, 17):
        p.drawRect(QRectF(x, 11, 2, 2.5))


def _access_point(p: QPainter) -> None:
    _dot(p, 12, 17, 1.4)
    for radius in (4.5, 8.5):
        p.drawArc(QRectF(12 - radius, 17 - radius, 2 * radius, 2 * radius), 45 * 16, 90 * 16)


def _nas(p: QPainter) -> None:
    _box(p, 4, 3, 16, 18)
    _line(p, 4, 9, 20, 9)
    _line(p, 4, 15, 20, 15)
    _dot(p, 8, 6)
    _dot(p, 8, 12)
    _dot(p, 8, 18)


def _server(p: QPainter) -> None:
    _box(p, 6, 2, 12, 20)
    _line(p, 6, 8, 18, 8)
    _line(p, 6, 14, 18, 14)
    _dot(p, 9, 5)
    _line(p, 9, 18, 15, 18)


def _raspberry_pi(p: QPainter) -> None:
    _box(p, 3, 6, 18, 12)
    p.drawRect(QRectF(9, 9, 6, 6))
    for x in (6, 10, 14, 18):
        _line(p, x, 6, x, 4)


def _workstation(p: QPainter) -> None:
    _box(p, 3, 4, 18, 12)
    _line(p, 12, 16, 12, 20)
    _line(p, 8, 20, 16, 20)


def _vm(p: QPainter) -> None:
    _box(p, 3, 3, 13, 13)
    _box(p, 8, 8, 13, 13)


def _container(p: QPainter) -> None:
    _poly(p, (12, 3), (20, 7.5), (20, 16.5), (12, 21), (4, 16.5), (4, 7.5))
    _line(p, 4, 7.5, 12, 12)
    _line(p, 20, 7.5, 12, 12)
    _line(p, 12, 12, 12, 21)


def _printer(p: QPainter) -> None:
    _box(p, 3, 9, 18, 8)
    p.drawRect(QRectF(7, 3, 10, 6))
    p.drawRect(QRectF(7, 14, 10, 6))


def _camera(p: QPainter) -> None:
    _box(p, 3, 8, 13, 9)
    _poly(p, (16, 12.5), (21, 9), (21, 16))


def _iot(p: QPainter) -> None:
    p.drawRect(QRectF(7, 7, 10, 10))
    for offset in (9.5, 14.5):
        _line(p, offset, 7, offset, 4)
        _line(p, offset, 17, offset, 20)
        _line(p, 7, offset, 4, offset)
        _line(p, 17, offset, 20, offset)


_GLYPHS: dict[str, Callable[[QPainter], None]] = {
    "internet": _internet,
    "modem": _modem,
    "router": _router,
    "firewall": _firewall,
    "switch": _switch,
    "access_point": _access_point,
    "nas": _nas,
    "server": _server,
    "raspberry_pi": _raspberry_pi,
    "workstation": _workstation,
    "vm": _vm,
    "container": _container,
    "printer": _printer,
    "camera": _camera,
    "iot": _iot,
}


def has_glyph(kind_key: str) -> bool:
    return kind_key in _GLYPHS


def paint_kind(painter: QPainter, kind_key: str, rect: QRectF, colour: QColor) -> None:
    """Draw the icon of a device kind inside ``rect``."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.topLeft())
    scale = min(rect.width(), rect.height()) / GRID
    painter.scale(scale, scale)
    pen = QPen(colour, 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    glyph = _GLYPHS.get(kind_key)
    if glyph is not None:
        glyph(painter)
    else:
        # A kind this build has no glyph for still gets a mark, so it is never invisible.
        _box(painter, 4, 4, 16, 16)
    painter.restore()


def render_kind(kind_key: str, colour: QColor, size: int = 24) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    paint_kind(painter, kind_key, QRectF(0, 0, size, size), colour)
    painter.end()
    return image


def kind_icon(kind_key: str, colour: QColor, size: int = 24) -> QIcon:
    return QIcon(QPixmap.fromImage(render_kind(kind_key, colour, size * 2)))


def app_image(size: int = 256) -> QImage:
    """The application icon: a small network on a rounded tile."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#2563eb"))
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    unit = size / GRID
    pen = QPen(QColor("#ffffff"), unit * 1.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    top, left, right = (
        QPointF(12 * unit, 6.5 * unit),
        QPointF(6 * unit, 17 * unit),
        QPointF(18 * unit, 17 * unit),
    )
    for a, b in ((top, left), (top, right), (left, right)):
        painter.drawLine(a, b)
    painter.setBrush(QColor("#ffffff"))
    for point in (top, left, right):
        painter.drawEllipse(point, unit * 2.2, unit * 2.2)
    painter.end()
    return image


def app_icon() -> QIcon:
    return QIcon(QPixmap.fromImage(app_image()))


if __name__ == "__main__":  # pragma: no cover - used by the build script
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m homelab_maker.gui.icons OUTPUT.ico")
    if not app_image().save(sys.argv[1]):
        raise SystemExit(f"could not write {sys.argv[1]}")
