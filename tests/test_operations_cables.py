"""Nesting and cables: the pure operations behind drawing them."""

import pytest

from homelab_maker.model import Endpoint, Medium, Project
from homelab_maker.operations import (
    add_interface,
    add_node,
    can_contain,
    connect,
    disconnect,
    free_interface,
    interface_links,
    move_into,
    move_out,
)
from homelab_maker.validation import validate


def build(*kinds: str) -> tuple[Project, list[str]]:
    project, ids = Project(), []
    for index, kind in enumerate(kinds):
        project, node_id = add_node(project, kind, index * 2, 0)
        ids.append(node_id)
    return project, ids


# ----------------------------------------------------------------------------- nesting


def test_a_virtual_machine_can_be_created_inside_a_nas() -> None:
    project, (nas,) = build("nas")
    project, vm = add_node(project, "vm", 0, 0, parent=nas)
    node = project.node(vm)
    assert node is not None and node.parent == nas
    assert validate(project) == []


def test_a_switch_cannot_be_created_inside_a_nas() -> None:
    project, (nas,) = build("nas")
    with pytest.raises(ValueError, match="a switch cannot sit inside a nas"):
        add_node(project, "switch", 0, 0, parent=nas)


def test_a_container_cannot_hold_anything() -> None:
    project, (nas,) = build("nas")
    project, container = add_node(project, "container", 0, 0, parent=nas)
    assert not can_contain(project, container, "container")


def test_a_child_cannot_be_created_inside_a_host_that_does_not_exist() -> None:
    with pytest.raises(ValueError, match="there is no node 'ghost'"):
        add_node(Project(), "vm", 0, 0, parent="ghost")


def test_children_of_two_hosts_may_use_the_same_cell() -> None:
    project, (first, second) = build("nas", "server")
    project, a = add_node(project, "vm", 0, 0, parent=first)
    project, b = add_node(project, "vm", 0, 0, parent=second)
    node_a, node_b = project.node(a), project.node(b)
    assert node_a is not None and node_b is not None
    assert (node_a.x, node_a.y) == (node_b.x, node_b.y) == (0, 0)
    assert validate(project) == []


def test_a_second_child_lands_on_a_free_cell_of_the_same_host() -> None:
    project, (nas,) = build("nas")
    project, _ = add_node(project, "vm", 0, 0, parent=nas)
    project, second = add_node(project, "vm", 0, 0, parent=nas)
    node = project.node(second)
    assert node is not None and (node.x, node.y) != (0, 0)
    assert validate(project) == []


def test_a_device_can_be_dropped_into_a_host_and_takes_a_free_cell() -> None:
    project, (nas, workstation) = build("nas", "workstation")
    project, vm = add_node(project, "vm", 5, 5)  # a loose VM on the canvas
    project = move_into(project, [vm], nas)
    node = project.node(vm)
    assert node is not None and node.parent == nas
    assert validate(project) == []
    assert workstation  # untouched


def test_a_host_carries_what_is_inside_it_when_it_is_put_inside_another() -> None:
    project, (nas,) = build("nas")
    project, vm = add_node(project, "vm", 0, 0, parent=nas)
    project, container = add_node(project, "container", 0, 0, parent=vm)
    project, server = add_node(project, "server", 4, 4)
    project = move_into(project, [vm], server)
    moved = project.node(container)
    assert moved is not None and moved.parent == vm
    assert [n.id for n in project.children(server)] == [vm]
    assert validate(project) == []


def test_a_device_cannot_be_put_inside_what_is_inside_it() -> None:
    project, (nas,) = build("nas")
    project, vm = add_node(project, "vm", 0, 0, parent=nas)
    with pytest.raises(ValueError, match="inside itself"):
        move_into(project, [nas], vm)


def test_a_switch_cannot_be_dropped_into_a_server() -> None:
    project, (server, switch) = build("server", "switch")
    with pytest.raises(ValueError, match="cannot sit inside"):
        move_into(project, [switch], server)


def test_nothing_to_move_is_an_error() -> None:
    with pytest.raises(ValueError, match="nothing to move"):
        move_into(Project(), ["ghost"], None)


def test_moving_out_puts_the_device_beside_its_former_host() -> None:
    project, (nas,) = build("nas")
    project, vm = add_node(project, "vm", 0, 0, parent=nas)
    project = move_out(project, [vm])
    node, host = project.node(vm), project.node(nas)
    assert node is not None and host is not None
    assert node.parent is None
    assert (node.x, node.y) != (host.x, host.y)  # not on top of the host
    assert validate(project) == []


def test_moving_out_of_a_vm_lands_inside_its_host() -> None:
    project, (nas,) = build("nas")
    project, vm = add_node(project, "vm", 0, 0, parent=nas)
    project, container = add_node(project, "container", 0, 0, parent=vm)
    project = move_out(project, [container])
    node = project.node(container)
    assert node is not None and node.parent == nas
    assert validate(project) == []


def test_moving_out_a_device_that_is_not_inside_anything_changes_nothing() -> None:
    project, (nas,) = build("nas")
    assert move_out(project, [nas]) == project


# ----------------------------------------------------------------------------- cables


def test_two_devices_are_joined_by_the_first_free_port_of_each() -> None:
    project, (switch, nas) = build("switch", "nas")
    project, link_id = connect(project, switch, nas)
    link = project.links[0]
    assert link.id == link_id
    ends = {(e.node, e.interface) for e in (link.a, link.b)}
    assert ends == {(switch, "port1"), (nas, "eth1")}
    assert validate(project) == []


def test_the_next_cable_uses_the_next_free_port() -> None:
    project, (switch, a, b) = build("switch", "nas", "server")
    project, _ = connect(project, switch, a)
    project, _ = connect(project, switch, b)
    used = sorted(
        e.interface for link in project.links for e in (link.a, link.b) if e.node == switch
    )
    assert used == ["port1", "port2"]
    assert validate(project) == []


def test_a_cable_can_name_the_ports_it_joins() -> None:
    project, (switch, nas) = build("switch", "nas")
    project, _ = connect(project, switch, nas, first_interface="port5", second_interface="eth2")
    assert interface_links(project, switch, "port5")
    assert interface_links(project, nas, "eth2")


def test_a_cable_cannot_go_on_a_port_that_has_one() -> None:
    project, (switch, a, b) = build("switch", "nas", "server")
    project, _ = connect(project, switch, a, first_interface="port1")
    with pytest.raises(ValueError, match="already has a cable"):
        connect(project, switch, b, first_interface="port1")


def test_a_full_device_refuses_one_more_cable() -> None:
    project, (nas, switch) = build("nas", "switch")
    project, _ = connect(project, nas, switch)
    project, _ = connect(project, nas, switch)
    with pytest.raises(ValueError, match="no free port"):
        connect(project, nas, switch)


def test_a_cable_to_a_port_that_does_not_exist_is_refused() -> None:
    project, (switch, nas) = build("switch", "nas")
    with pytest.raises(ValueError, match="no port 'port99'"):
        connect(project, switch, nas, first_interface="port99")


def test_a_device_cannot_be_cabled_to_itself_or_to_something_missing() -> None:
    project, (switch,) = build("switch")
    with pytest.raises(ValueError, match="to itself"):
        connect(project, switch, switch)
    with pytest.raises(ValueError, match="there is no node 'ghost'"):
        connect(project, switch, "ghost")


def test_a_guest_cannot_be_cabled_to_its_own_host() -> None:
    project, (nas,) = build("nas")
    project, vm = add_node(project, "vm", 0, 0, parent=nas)
    with pytest.raises(ValueError, match="already attached"):
        connect(project, nas, vm)


def test_a_wireless_link_gets_an_interface_of_its_own_instead_of_a_cabled_port() -> None:
    project, (ap, laptop, switch) = build("access_point", "workstation", "switch")
    project, _ = connect(project, ap, switch)  # uses the AP's only port
    project, link_id = connect(project, ap, laptop, Medium.WIFI)
    link = next(link for link in project.links if link.id == link_id)
    assert {link.a.interface, link.b.interface} == {"wlan0"}
    assert free_interface(project, ap, Medium.ETHERNET) is None
    assert validate(project) == []


def test_many_wireless_links_share_the_radio_of_the_access_point() -> None:
    project, (ap, one, two) = build("access_point", "workstation", "workstation")
    project, _ = connect(project, ap, one, Medium.WIFI)
    project, _ = connect(project, ap, two, Medium.WIFI)
    node = project.node(ap)
    assert node is not None
    assert [i.name for i in node.interfaces] == ["eth1", "wlan0"]
    assert validate(project) == []


def test_a_tunnel_gets_a_tun_interface_and_does_not_take_a_cabled_port() -> None:
    project, (server, firewall) = build("server", "firewall")
    project, _ = connect(project, server, firewall, Medium.VPN)
    node = project.node(server)
    assert node is not None and "tun0" in [i.name for i in node.interfaces]
    assert free_interface(project, server, Medium.ETHERNET) == "eth1"
    assert validate(project) == []


def test_a_port_with_a_wireless_link_is_not_offered_to_a_cable() -> None:
    project, (ap, laptop, switch) = build("access_point", "workstation", "switch")
    project, _ = connect(project, ap, laptop, Medium.WIFI, first_interface="eth1")
    with pytest.raises(ValueError, match="already has a link"):
        connect(project, ap, switch, first_interface="eth1")


def test_a_radio_that_is_cabled_is_not_reused_for_wireless() -> None:
    project, (ap, laptop, switch) = build("access_point", "workstation", "switch")
    project, name = add_interface(project, ap, "wlan0")
    project, _ = connect(project, ap, switch, first_interface="wlan0")
    with pytest.raises(ValueError, match="already has a cable"):
        connect(project, ap, laptop, Medium.WIFI, first_interface=name)


def test_link_ids_do_not_clash() -> None:
    project, (switch, a) = build("switch", "nas")
    project, first = connect(project, switch, a)
    project, second = connect(project, switch, a)
    assert first != second


def test_a_cable_is_removed_and_its_port_is_free_again() -> None:
    project, (switch, nas) = build("switch", "nas")
    project, link_id = connect(project, switch, nas)
    project = disconnect(project, [link_id])
    assert project.links == ()
    assert free_interface(project, switch, Medium.ETHERNET) == "port1"


def test_removing_a_cable_that_does_not_exist_is_an_error() -> None:
    with pytest.raises(ValueError, match="there is no link 'nope'"):
        disconnect(Project(), ["nope"])


def test_interface_links_finds_a_link_from_either_end() -> None:
    project, (switch, nas) = build("switch", "nas")
    project, _ = connect(project, switch, nas)
    assert interface_links(project, switch, "port1") == interface_links(project, nas, "eth1")
    assert interface_links(project, switch, "port2") == ()
    assert Endpoint(nas, "eth1") in (project.links[0].a, project.links[0].b)


# ----------------------------------------------------------------------------- ports


def test_a_new_port_is_named_after_the_kind_and_the_next_free_number() -> None:
    project, (nas,) = build("nas")  # eth1, eth2
    project, name = add_interface(project, nas)
    assert name == "eth3"
    project, other = add_interface(project, nas, "mgmt")
    assert other == "mgmt"


def test_a_port_name_cannot_be_used_twice() -> None:
    project, (nas,) = build("nas")
    with pytest.raises(ValueError, match="already has a port named 'eth1'"):
        add_interface(project, nas, "eth1")


def test_a_port_cannot_be_added_to_a_missing_device() -> None:
    with pytest.raises(ValueError, match="there is no node"):
        add_interface(Project(), "ghost")
