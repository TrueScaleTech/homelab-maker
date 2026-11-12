"""Grid geometry: how whole cells map to canvas coordinates. Pure arithmetic, no Qt."""

import itertools
import math
from collections.abc import Sequence

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


def point_along(points: Sequence[tuple[float, float]], progress: float) -> tuple[float, float]:
    """The spot ``progress`` (0 to 1) of the way along a line through ``points``.

    The line is measured by length, so a packet moves at one speed along all of it.
    """
    if not points:
        raise ValueError("a line needs at least one point")
    progress = max(0.0, min(1.0, progress))
    lengths = [math.dist(a, b) for a, b in itertools.pairwise(points)]
    total = sum(lengths)
    if total == 0:
        return points[0]
    remaining = progress * total
    for (a, b), length in zip(itertools.pairwise(points), lengths, strict=True):
        if remaining <= length and length > 0:
            ratio = remaining / length
            return a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio
        remaining -= length
    return points[-1]
