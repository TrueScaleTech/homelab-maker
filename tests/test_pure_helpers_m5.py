"""Small pure helpers behind the flow view: geometry, cards of a path, text of a rule."""

import math

import pytest

from homelab_maker.fields import parse_port, parse_reference
from homelab_maker.grid import point_along
from homelab_maker.model import Project
from homelab_maker.viewmodel import path_cards, reference_label

# ----------------------------------------------------------------------- point_along


def test_a_packet_starts_at_the_start_and_ends_at_the_end() -> None:
    line = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    assert point_along(line, 0) == (0.0, 0.0)
    assert point_along(line, 1) == (10.0, 10.0)


def test_a_packet_moves_at_one_speed_along_the_whole_line() -> None:
    line = [(0.0, 0.0), (10.0, 0.0), (10.0, 30.0)]  # 10 across, then 30 down
    x, y = point_along(line, 0.25)  # a quarter of 40 is exactly the corner
    assert (x, y) == pytest.approx((10.0, 0.0))
    x, y = point_along(line, 0.5)
    assert (x, y) == pytest.approx((10.0, 10.0))


def test_progress_outside_zero_to_one_is_held_at_the_ends() -> None:
    line = [(0.0, 0.0), (4.0, 3.0)]
    assert point_along(line, -3) == (0.0, 0.0)
    assert point_along(line, 7) == (4.0, 3.0)
    assert math.dist(point_along(line, 0.5), (2.0, 1.5)) < 1e-9


def test_a_line_of_one_point_or_of_zero_length_stays_put() -> None:
    assert point_along([(3.0, 4.0)], 0.5) == (3.0, 4.0)
    assert point_along([(3.0, 4.0), (3.0, 4.0)], 0.5) == (3.0, 4.0)


def test_a_line_with_a_repeated_point_is_walked_through() -> None:
    line = [(0.0, 0.0), (0.0, 0.0), (10.0, 0.0)]
    assert point_along(line, 0.5) == pytest.approx((5.0, 0.0))


def test_no_points_is_an_error() -> None:
    with pytest.raises(ValueError, match="at least one point"):
        point_along([], 0.5)


# ----------------------------------------------------------------------- path_cards


def test_a_path_through_a_guest_is_the_host_card_from_the_canvas(sample: Project) -> None:
    path = ("laptop", "ap", "switch", "nas", "home-assistant")
    assert path_cards(sample, None, path) == ("laptop", "ap", "switch", "nas")


def test_inside_a_host_the_part_outside_it_is_left_out(sample: Project) -> None:
    path = ("laptop", "ap", "switch", "nas", "home-assistant")
    assert path_cards(sample, "nas", path) == ("home-assistant",)


def test_a_path_is_shown_one_level_deeper_inside_a_vm(sample: Project) -> None:
    path = ("desktop", "switch", "nas", "docker-host", "nextcloud")
    assert path_cards(sample, "nas", path) == ("docker-host",)
    assert path_cards(sample, "docker-host", path) == ("nextcloud",)


def test_an_empty_path_has_no_cards(sample: Project) -> None:
    assert path_cards(sample, None, ()) == ()


# ------------------------------------------------------------------------ references


def test_a_rule_may_name_a_device_by_id_or_by_name(sample: Project) -> None:
    assert parse_reference(sample, "nas") == "nas"
    assert parse_reference(sample, "truenas") == "nas"
    assert parse_reference(sample, " Core Switch ") == "switch"


def test_a_rule_may_say_any_or_name_a_network(sample: Project) -> None:
    assert parse_reference(sample, "ANY") == "any"
    assert parse_reference(sample, "192.168.10.0/24") == "192.168.10.0/24"


@pytest.mark.parametrize("text", ["", "   ", "nobody"])
def test_a_reference_that_means_nothing_is_refused(sample: Project, text: str) -> None:
    with pytest.raises(ValueError):
        parse_reference(sample, text)


def test_a_reference_is_shown_by_name_when_it_is_a_device(sample: Project) -> None:
    assert reference_label(sample, "nas") == "TrueNAS"
    assert reference_label(sample, "any") == "any"
    assert reference_label(sample, "10.0.0.0/8") == "10.0.0.0/8"


# ---------------------------------------------------------------------------- ports


def test_a_port_is_a_number_or_any() -> None:
    assert parse_port("443") == 443
    assert parse_port("") is None
    assert parse_port("Any") is None


@pytest.mark.parametrize("text", ["0", "65536", "http", "-1", "4.5"])
def test_a_bad_port_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="1 to 65535"):
        parse_port(text)
