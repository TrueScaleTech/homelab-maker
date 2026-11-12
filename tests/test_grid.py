import pytest

from homelab_maker.grid import CELL, ZOOM_MAX, ZOOM_MIN, cell_at, cell_origin, clamp_zoom, snap
from homelab_maker.model import GRID_LIMIT


def test_a_cell_and_its_origin_agree() -> None:
    for cell in [(0, 0), (3, -2), (-5, 7)]:
        px, py = cell_origin(*cell)
        assert cell_at(px, py) == cell
        assert cell_at(px + CELL - 1, py + CELL - 1) == cell


def test_the_cell_just_left_of_zero_is_minus_one() -> None:
    assert cell_at(-0.5, -0.5) == (-1, -1)


def test_cell_at_never_leaves_the_grid_the_model_allows() -> None:
    assert cell_at(1e12, -1e12) == (GRID_LIMIT, -GRID_LIMIT)


def test_snap_goes_to_the_nearest_cell_corner() -> None:
    assert snap(CELL * 0.4, CELL * 0.4) == (0, 0)
    assert snap(CELL * 0.6, CELL * 0.6) == (CELL, CELL)
    assert snap(-CELL * 0.6, 0) == (-CELL, 0)


@pytest.mark.parametrize(
    ("current", "factor", "expected"),
    [(1.0, 1.25, 1.25), (1.0, 100.0, ZOOM_MAX), (1.0, 0.0001, ZOOM_MIN), (ZOOM_MAX, 2.0, ZOOM_MAX)],
)
def test_zoom_stays_between_its_limits(current: float, factor: float, expected: float) -> None:
    assert clamp_zoom(current, factor) == pytest.approx(expected)
