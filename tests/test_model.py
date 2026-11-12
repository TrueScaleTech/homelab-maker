from dataclasses import replace

import pytest

from homelab_maker.model import (
    Endpoint,
    Flow,
    Interface,
    InterfaceMode,
    Link,
    Medium,
    Node,
    Project,
    Protocol,
    Rule,
    RuleAction,
    RuleProtocol,
    Service,
    Zone,
    new_node,
    node_routes,
    slugify,
    unique_id,
)

# ------------------------------------------------------------------------- interfaces


def test_an_address_without_a_prefix_is_a_single_host() -> None:
    assert Interface("eth1", ("192.168.1.5",)).addresses == ("192.168.1.5/32",)


def test_a_netmask_is_turned_into_a_prefix_length() -> None:
    assert Interface("eth1", ("192.168.1.5/255.255.255.0",)).addresses == ("192.168.1.5/24",)


def test_ipv6_is_accepted() -> None:
    assert Interface("eth1", ("fd00::5/64",)).addresses == ("fd00::5/64",)


@pytest.mark.parametrize("bad", ["", "nas.home", "192.168.1.5/33", "300.1.1.1", "192.168.1"])
def test_a_malformed_address_cannot_be_built(bad: str) -> None:
    with pytest.raises(ValueError, match="not an IPv4 or IPv6 address"):
        Interface("eth1", (bad,))


def test_the_same_address_twice_is_refused() -> None:
    with pytest.raises(ValueError, match="same address twice"):
        Interface("eth1", ("10.0.0.5/24", "10.0.0.5/24"))


@pytest.mark.parametrize("vlan", [0, 4095, -1, True])
def test_a_vlan_outside_the_valid_range_is_refused(vlan: int) -> None:
    with pytest.raises(ValueError, match="VLAN"):
        Interface("eth1", vlan=vlan)


def test_tagged_vlans_are_sorted_and_deduplicated_on_a_trunk() -> None:
    trunk = Interface("port3", mode=InterfaceMode.TRUNK, vlan=10, trunk_vlans=(30, 20, 20))
    assert trunk.trunk_vlans == (20, 30)


def test_an_access_port_cannot_carry_tagged_vlans() -> None:
    with pytest.raises(ValueError, match="only a trunk"):
        Interface("port3", trunk_vlans=(20,))


def test_a_mode_given_as_plain_text_is_understood() -> None:
    assert Interface("eth1", mode="trunk").mode is InterfaceMode.TRUNK  # type: ignore[arg-type]


def test_an_unknown_mode_is_refused() -> None:
    with pytest.raises(ValueError, match="InterfaceMode"):
        Interface("eth1", mode="hybrid")  # type: ignore[arg-type]


# ------------------------------------------------------------------ services and rules


@pytest.mark.parametrize("port", [0, 65536, True])
def test_a_service_port_must_be_a_real_port(port: int) -> None:
    with pytest.raises(ValueError, match="port"):
        Service("web", port)


def test_a_rule_network_is_normalised() -> None:
    assert Rule(RuleAction.DENY, "192.168.1.7/24").source == "192.168.1.0/24"


def test_a_rule_can_name_a_node_or_anything() -> None:
    rule = Rule(RuleAction.ALLOW, "nas", "any")
    assert (rule.source, rule.destination) == ("nas", "any")


@pytest.mark.parametrize("bad", ["Not An Id", "192.168.1.0/33", "", "nas/home"])
def test_a_rule_endpoint_must_be_any_a_network_or_an_id(bad: str) -> None:
    with pytest.raises(ValueError, match="must be 'any'"):
        Rule(RuleAction.ALLOW, bad)


def test_a_port_needs_tcp_or_udp() -> None:
    with pytest.raises(ValueError, match="needs the protocol"):
        Rule(RuleAction.ALLOW, protocol=RuleProtocol.ICMP, port=8)
    with pytest.raises(ValueError, match="needs the protocol"):
        Rule(RuleAction.ALLOW, port=443)
    assert Rule(RuleAction.ALLOW, protocol="tcp", port=443).port == 443  # type: ignore[arg-type]


# ---------------------------------------------------------------------------- nodes


def test_the_word_any_cannot_be_a_node_id() -> None:
    with pytest.raises(ValueError, match="reserved"):
        Node("any", "nas", "Anything")


@pytest.mark.parametrize("bad", ["", "Nas", "my nas", "-nas", "nas.home", "x" * 64])
def test_a_node_id_is_a_short_lowercase_slug(bad: str) -> None:
    with pytest.raises(ValueError, match="node id"):
        Node(bad, "nas", "NAS")


def test_a_name_cannot_be_empty_or_hold_control_characters() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        Node("nas", "nas", "   ")
    with pytest.raises(ValueError, match="control characters"):
        Node("nas", "nas", "NAS\x00")


def test_a_name_must_be_text() -> None:
    with pytest.raises(ValueError, match="must be text"):
        Node("nas", "nas", 5)  # type: ignore[arg-type]


def test_a_position_stays_within_the_grid() -> None:
    with pytest.raises(ValueError, match="between"):
        Node("nas", "nas", "NAS", x=10_001)


def test_routes_must_be_a_real_boolean_or_unset() -> None:
    with pytest.raises(ValueError, match="routes"):
        Node("vm1", "vm", "VM", routes=1)  # type: ignore[arg-type]


def test_nodes_that_forward_follow_the_kind_unless_told_otherwise() -> None:
    assert node_routes(Node("gw", "firewall", "Gateway"))
    assert not node_routes(Node("vm1", "vm", "VM"))
    assert node_routes(Node("vm1", "vm", "OPNsense", routes=True))
    assert not node_routes(Node("gw", "firewall", "Bridge", routes=False))
    assert not node_routes(Node("x", "no_such_kind", "Mystery"))


# ------------------------------------------------------------- links, zones and flows


def test_a_link_is_the_same_from_either_end() -> None:
    forward = Link("l1", Endpoint("a", "eth1"), Endpoint("b", "eth1"))
    backward = Link("l1", Endpoint("b", "eth1"), Endpoint("a", "eth1"))
    assert forward == backward
    assert backward.a.node == "a"


def test_a_link_speed_must_be_positive() -> None:
    with pytest.raises(ValueError, match="speed"):
        Link("l1", Endpoint("a", "eth1"), Endpoint("b", "eth1"), speed_mbps=0)


def test_an_unknown_medium_is_refused() -> None:
    with pytest.raises(ValueError, match="Medium"):
        Link("l1", Endpoint("a", "eth1"), Endpoint("b", "eth1"), medium="carrier-pigeon")  # type: ignore[arg-type]
    assert Link("l1", Endpoint("a", "e"), Endpoint("b", "e"), medium="wifi").medium is Medium.WIFI  # type: ignore[arg-type]


def test_a_zone_needs_a_size() -> None:
    with pytest.raises(ValueError, match="width"):
        Zone("lan", "LAN", 0, 0, 0, 3)


def test_a_flow_needs_a_real_port_and_a_short_description() -> None:
    with pytest.raises(ValueError, match="port"):
        Flow("f1", "a", "b", 0)
    with pytest.raises(ValueError, match="description"):
        Flow("f1", "a", "b", 80, description="x" * 201)
    assert Flow("f1", "a", "b", 80).protocol is Protocol.TCP


# --------------------------------------------------------------------------- project


def test_collections_are_kept_sorted_by_id() -> None:
    nodes = (Node("b", "nas", "B"), Node("a", "nas", "A", x=1))
    assert [n.id for n in Project(nodes=nodes).nodes] == ["a", "b"]


def test_equal_homelabs_compare_equal_whatever_the_order_they_were_built_in() -> None:
    one = Project(nodes=(Node("a", "nas", "A"), Node("b", "nas", "B", x=1)))
    two = Project(nodes=(Node("b", "nas", "B", x=1), Node("a", "nas", "A")))
    assert one == two


def test_the_order_of_rules_is_kept_because_the_first_match_wins() -> None:
    deny, allow = Rule(RuleAction.DENY, "10.0.0.0/8"), Rule(RuleAction.ALLOW)
    assert Node("gw", "firewall", "GW", rules=(deny, allow)).rules == (deny, allow)
    assert Node("gw", "firewall", "GW", rules=[allow, deny]).rules == (allow, deny)  # type: ignore[arg-type]


def test_children_are_found_by_parent() -> None:
    host = Node("nas", "nas", "NAS")
    vm = Node("vm1", "vm", "VM", parent="nas")
    other = Node("pc", "workstation", "PC", x=2)
    project = Project(nodes=(host, vm, other))
    assert project.children("nas") == (vm,)
    assert project.children(None) == (host, other)
    assert project.node("vm1") == vm
    assert project.node("missing") is None


def test_changing_a_project_leaves_the_old_one_untouched() -> None:
    before = Project(nodes=(Node("a", "nas", "A"),))
    after = replace(before, nodes=(*before.nodes, Node("b", "nas", "B", x=1)))
    assert len(before.nodes) == 1
    assert len(after.nodes) == 2


# ------------------------------------------------------------------------ new nodes


def test_slugify_makes_a_usable_start_for_an_id() -> None:
    assert slugify("Home Assistant!") == "home-assistant"
    assert slugify("  --  ") == "item"
    assert slugify("Zürich ünit") == "z-rich-nit"
    assert len(slugify("x" * 100)) <= 40


def test_unique_id_counts_up_until_it_is_free() -> None:
    assert unique_id([], "nas") == "nas"
    assert unique_id(["nas"], "nas") == "nas-2"
    assert unique_id(["nas", "nas-2"], "nas") == "nas-3"


def test_a_new_switch_starts_with_its_eight_named_ports() -> None:
    switch = new_node("switch", "Core switch", [], x=3, y=1)
    assert switch.id == "core-switch"
    assert [i.name for i in switch.interfaces] == [f"port{n}" for n in range(1, 9)]
    assert (switch.x, switch.y) == (3, 1)


def test_a_new_node_never_reuses_an_id() -> None:
    assert new_node("nas", "NAS", ["nas"]).id == "nas-2"


def test_a_new_node_of_an_unknown_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown device kind"):
        new_node("toaster", "Toaster", [])
