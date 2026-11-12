"""Grid geometry: how whole cells map to canvas coordinates. Pure arithmetic, no Qt."""

import math

from homelab_maker.model import GRID_LIMIT

# One grid cell, in canvas units. A device card is a little smaller than a cell.
CELL = 112

ZOOM_MIN = 0.25
ZOOM_MAX = 3.0


def cell_origin(x: int, y: int) -> tuple[int, int]:
    """The top-left corner of a cell, in canvas units."""
    return x * CELL, y * CELL


def cell_at(px: float, py: float) -> tuple[int, int]:
    """The cell that contains a canvas point, kept inside the limits the model allows."""
    return (
        max(-GRID_LIMIT, min(GRID_LIMIT, math.floor(px / CELL))),
        max(-GRID_LIMIT, min(GRID_LIMIT, math.floor(py / CELL))),
    )


def snap(px: float, py: float) -> tuple[int, int]:
    """The top-left corner of the cell nearest to a card's top-left corner."""
    x, y = (
        max(-GRID_LIMIT, min(GRID_LIMIT, round(px / CELL))),
        max(-GRID_LIMIT, min(GRID_LIMIT, round(py / CELL))),
    )
    return cell_origin(x, y)


def clamp_zoom(current: float, factor: float) -> float:
    """The zoom after multiplying by ``factor``, kept between the limits."""
    return max(ZOOM_MIN, min(ZOOM_MAX, current * factor))
