from pathlib import Path

import pytest

from homelab_maker.model import Endpoint, Link, Medium, Node, Project
from homelab_maker.viewmodel import (
    drawn_links,
    inside_count,
    project_path,
    root_of,
    status_text,
    window_title,
)


@pytest.mark.parametrize(
    ("typed", "saved_as"),
    [
        ("lab", "lab.homelab.json"),
        ("lab.homelab.json", "lab.homelab.json"),
        ("lab.json", "lab.homelab.json"),
        ("lab.JSON", "lab.homelab.json"),
        ("my.lab", "my.lab.homelab.json"),
    ],
)
def test_a_project_is_always_saved_with_the_project_suffix(typed: str, saved_as: str) -> None:
    assert project_path(Path("dir") / typed) == Path("dir") / saved_as


def test_the_title_names_the_file_and_marks_unsaved_changes() -> None:
    assert window_title(None, False) == "Untitled — HomeLabMaker"
    assert window_title(Path("a/lab.homelab.json"), False) == "lab.homelab.json — HomeLabMaker"
    assert window_title(Path("a/lab.homelab.json"), True).startswith("*lab.homelab.json")


def test_the_status_line_counts_with_the_right_plural() -> None:
    assert status_text(Project(), 0) == "0 devices · 0 links"
    one = Project(nodes=(Node("a", "nas", "A"),))
    assert status_text(one, 0) == "1 device · 0 links"
    assert status_text(one, 1) == "1 device · 0 links · 1 selected"


def test_the_outermost_host_is_found_at_any_depth(sample: Project) -> None:
    assert root_of(sample, "nas") == "nas"
    assert root_of(sample, "docker-host") == "nas"
    assert root_of(sample, "nextcloud") == "nas"
    assert root_of(sample, "ghost") is None


def test_root_of_does_not_loop_on_a_broken_project() -> None:
    # Such a project is refused on load; the helper still must not hang if it is handed one.
    broken = Project(nodes=(Node("a", "nas", "A", parent="b"), Node("b", "nas", "B", parent="a")))
    assert root_of(broken, "a") in {"a", "b"}


def test_a_host_knows_how_many_things_sit_inside_it(sample: Project) -> None:
    assert inside_count(sample, "nas") == 4  # two VMs and two containers
    assert inside_count(sample, "docker-host") == 2
    assert inside_count(sample, "switch") == 0
    assert inside_count(sample, "ghost") == 0


def test_every_link_of_the_example_is_drawn_between_two_cards(sample: Project) -> None:
    links = drawn_links(sample)
    assert len(links) == len(sample.links) == 9
    cards = {node.id for node in sample.children(None)}
    assert all(link.a in cards and link.b in cards for link in links)


def test_a_link_ends_on_the_host_that_contains_the_node() -> None:
    project = Project(
        nodes=(
            Node("nas", "nas", "NAS"),
            Node("vm1", "vm", "VM", parent="nas"),
            Node("sw", "switch", "Switch", x=3),
        ),
        links=(Link("l1", Endpoint("sw", "port1"), Endpoint("vm1", "vnic1")),),
    )
    (link,) = drawn_links(project)
    assert {link.a, link.b} == {"nas", "sw"}


def test_a_link_between_two_things_in_one_host_is_not_drawn() -> None:
    project = Project(
        nodes=(
            Node("nas", "nas", "NAS"),
            Node("vm1", "vm", "VM1", parent="nas"),
            Node("vm2", "vm", "VM2", x=1, parent="nas"),
        ),
        links=(Link("l1", Endpoint("vm1", "vnic1"), Endpoint("vm2", "vnic1"), Medium.VPN),),
    )
    assert drawn_links(project) == ()
