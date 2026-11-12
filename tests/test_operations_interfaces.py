"""Editing the settings of a port."""

import pytest

from homelab_maker.model import InterfaceMode, Project
from homelab_maker.operations import (
    add_node,
    connect,
    remove_interface,
    rename_interface,
    set_addresses,
    set_mode,
    set_trunk_vlans,
    set_vlan,
)
from homelab_maker.validation import validate


def switch() -> Project:
    project, _ = add_node(Project(), "switch", 0, 0)
    return project


def port(project: Project, name: str = "port1") -> object:
    node = project.node("switch")
    assert node is not None
    return next(i for i in node.interfaces if i.name == name)


def test_a_port_gets_addresses() -> None:
    project = set_addresses(switch(), "switch", "port1", ["192.168.1.2/24", "fd00::2/64"])
    assert port(project).addresses == ("192.168.1.2/24", "fd00::2/64")  # type: ignore[attr-defined]


def test_a_bad_address_changes_nothing() -> None:
    original = switch()
    with pytest.raises(ValueError, match="not an IPv4 or IPv6 address"):
        set_addresses(original, "switch", "port1", ["not-an-address"])
    assert port(original).addresses == ()  # type: ignore[attr-defined]


def test_the_same_address_twice_on_one_port_is_refused() -> None:
    with pytest.raises(ValueError, match="same address twice"):
        set_addresses(switch(), "switch", "port1", ["10.0.0.1/24", "10.0.0.1/24"])


def test_a_port_gets_a_vlan_and_loses_it_again() -> None:
    project = set_vlan(switch(), "switch", "port1", 20)
    assert port(project).vlan == 20  # type: ignore[attr-defined]
    assert port(set_vlan(project, "switch", "port1", None)).vlan is None  # type: ignore[attr-defined]


def test_a_vlan_out_of_range_is_refused() -> None:
    with pytest.raises(ValueError, match="between 1 and 4094"):
        set_vlan(switch(), "switch", "port1", 5000)


def test_only_a_trunk_lists_tagged_vlans() -> None:
    with pytest.raises(ValueError, match="only a trunk"):
        set_trunk_vlans(switch(), "switch", "port1", [10, 20])
    project = set_mode(switch(), "switch", "port1", InterfaceMode.TRUNK)
    project = set_trunk_vlans(project, "switch", "port1", [20, 10, 20])
    assert port(project).trunk_vlans == (10, 20)  # type: ignore[attr-defined]


def test_switching_a_trunk_back_to_access_drops_its_tagged_vlans() -> None:
    project = set_mode(switch(), "switch", "port1", InterfaceMode.TRUNK)
    project = set_trunk_vlans(project, "switch", "port1", [10, 20])
    project = set_mode(project, "switch", "port1", InterfaceMode.ACCESS)
    assert port(project).trunk_vlans == ()  # type: ignore[attr-defined]
    assert port(project).mode is InterfaceMode.ACCESS  # type: ignore[attr-defined]


def test_a_missing_port_or_device_is_an_error() -> None:
    with pytest.raises(ValueError, match="has no port 'nope'"):
        set_vlan(switch(), "switch", "nope", 10)
    with pytest.raises(ValueError, match="there is no node 'ghost'"):
        set_vlan(switch(), "ghost", "port1", 10)


def test_renaming_a_port_moves_the_cable_that_ends_on_it() -> None:
    project, _ = add_node(switch(), "nas", 4, 0)
    project, _ = connect(project, "switch", "nas")
    project = rename_interface(project, "switch", "port1", "uplink")
    link = project.links[0]
    assert "uplink" in (link.a.interface, link.b.interface)
    assert validate(project) == []


def test_a_port_cannot_take_the_name_of_another() -> None:
    with pytest.raises(ValueError, match="already has a port named 'port2'"):
        rename_interface(switch(), "switch", "port1", "port2")


def test_renaming_a_port_to_its_own_name_is_harmless() -> None:
    original = switch()
    assert rename_interface(original, "switch", "port1", "port1") == original


def test_a_port_that_does_not_exist_cannot_be_renamed() -> None:
    with pytest.raises(ValueError, match="there is no node"):
        rename_interface(switch(), "ghost", "port1", "x")


def test_a_free_port_is_removed() -> None:
    project = remove_interface(switch(), "switch", "port8")
    node = project.node("switch")
    assert node is not None and len(node.interfaces) == 7


def test_a_port_with_a_cable_is_not_removed() -> None:
    project, _ = add_node(switch(), "nas", 4, 0)
    project, _ = connect(project, "switch", "nas")
    with pytest.raises(ValueError, match="remove the cable first"):
        remove_interface(project, "switch", "port1")


def test_removing_a_port_that_is_not_there_is_an_error() -> None:
    with pytest.raises(ValueError, match="has no port 'nope'"):
        remove_interface(switch(), "switch", "nope")
    with pytest.raises(ValueError, match="there is no node"):
        remove_interface(switch(), "ghost", "port1")
