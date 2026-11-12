"""Looking inside a host: which card stands for a node, and which cables a view shows."""

from dataclasses import replace

from homelab_maker.model import Endpoint, Link, Node, Project
from homelab_maker.viewmodel import drawn_links, shown_as, trail, trail_text


def test_a_node_in_the_view_is_shown_as_itself(sample: Project) -> None:
    assert shown_as(sample, "nas", None) == "nas"


def test_a_node_in_a_host_is_shown_as_the_host_on_the_canvas(sample: Project) -> None:
    assert shown_as(sample, "nextcloud", None) == "nas"


def test_inside_the_host_each_level_shows_the_next_card_down(sample: Project) -> None:
    assert shown_as(sample, "nextcloud", "nas") == "docker-host"
    assert shown_as(sample, "nextcloud", "docker-host") == "nextcloud"


def test_a_node_outside_the_view_is_not_shown_in_it(sample: Project) -> None:
    assert shown_as(sample, "switch", "nas") is None
    assert shown_as(sample, "ghost", None) is None


def test_a_broken_parent_loop_does_not_hang() -> None:
    loop = Project(
        nodes=(Node("a", "vm", "A", parent="b"), Node("b", "vm", "B", parent="a")),
    )
    assert shown_as(loop, "a", None) is None


def test_the_trail_names_every_level(sample: Project) -> None:
    assert trail(sample, None) == ((None, sample.name),)
    assert trail(sample, "docker-host") == (
        (None, sample.name),
        ("nas", "TrueNAS"),
        ("docker-host", "Docker host"),
    )
    assert trail_text(sample, "nas") == f"{sample.name} / TrueNAS"


def test_the_canvas_view_draws_the_cable_to_the_host_that_holds_a_guest(sample: Project) -> None:
    guest_link = Link(
        "guest",
        Endpoint("nextcloud", "veth1"),
        Endpoint("switch", "port8"),
    )
    project = replace(sample, links=(*sample.links, guest_link))
    drawn = {link.id: (link.a, link.b) for link in drawn_links(project)}
    assert set(drawn["guest"]) == {"nas", "switch"}


def test_a_cable_between_two_guests_is_drawn_inside_their_host_only() -> None:
    project = Project(
        nodes=(
            Node("host", "nas", "Host"),
            Node("one", "vm", "One", parent="host"),
            Node("two", "vm", "Two", x=1, parent="host"),
        ),
        links=(Link("l", Endpoint("one", "vnic1"), Endpoint("two", "vnic1")),),
    )
    assert drawn_links(project, None) == ()
    assert [link.id for link in drawn_links(project, "host")] == ["l"]


def test_a_cable_leaving_the_host_is_not_drawn_inside_it(sample: Project) -> None:
    ids = {link.id for link in drawn_links(sample, "nas")}
    assert "switch-nas" not in ids
