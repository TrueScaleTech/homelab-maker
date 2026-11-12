from dataclasses import replace

from homelab_maker.model import (
    Endpoint,
    Flow,
    Interface,
    Link,
    Medium,
    Node,
    Project,
    Rule,
    RuleAction,
    new_node,
)
from homelab_maker.validation import Code, validate


def codes(project: Project) -> list[Code]:
    return [problem.code for problem in validate(project)]


def cable(
    link_id: str, a: tuple[str, str], b: tuple[str, str], medium: Medium = Medium.ETHERNET
) -> Link:
    return Link(link_id, Endpoint(*a), Endpoint(*b), medium)


def test_the_shipped_example_is_consistent(sample: Project) -> None:
    assert validate(sample) == []


def test_an_empty_project_is_consistent() -> None:
    assert validate(Project()) == []


# -------------------------------------------------------------------------------- ids


def test_a_repeated_node_id_is_reported() -> None:
    project = Project(nodes=(Node("a", "nas", "One"), Node("a", "nas", "Two", x=1)))
    assert Code.DUPLICATE_ID in codes(project)


def test_a_repeated_link_flow_or_zone_id_is_reported() -> None:
    nodes = (new_node("switch", "S", []), new_node("nas", "N", ["s"], x=1))
    link = cable("l1", ("s", "port1"), ("n", "eth1"))
    flow = Flow("f1", "s", "n", 80)
    project = Project(nodes=nodes, links=(link, replace(link)), flows=(flow, flow))
    assert codes(project).count(Code.DUPLICATE_ID) >= 2


# ------------------------------------------------------------------------ the kind


def test_an_unknown_kind_is_reported() -> None:
    assert codes(Project(nodes=(Node("t", "toaster", "Toaster"),))) == [Code.UNKNOWN_KIND]


# ---------------------------------------------------------------------------- nesting


def host_and_guest() -> tuple[Node, Node]:
    return Node("nas", "nas", "NAS"), Node("vm1", "vm", "VM", parent="nas")


def test_a_vm_inside_a_nas_is_fine() -> None:
    assert validate(Project(nodes=host_and_guest())) == []


def test_a_parent_that_does_not_exist_is_reported() -> None:
    project = Project(nodes=(Node("vm1", "vm", "VM", parent="ghost"),))
    assert codes(project) == [Code.UNKNOWN_PARENT]


def test_a_container_cannot_hold_a_vm() -> None:
    project = Project(
        nodes=(
            Node("c1", "container", "Container"),
            Node("vm1", "vm", "VM", parent="c1"),
        )
    )
    assert codes(project) == [Code.BAD_NESTING]


def test_a_switch_cannot_hold_anything() -> None:
    project = Project(
        nodes=(Node("sw", "switch", "Switch"), Node("c1", "container", "Container", parent="sw"))
    )
    assert codes(project) == [Code.BAD_NESTING]


def test_a_node_cannot_be_its_own_parent() -> None:
    project = Project(nodes=(Node("vm1", "vm", "VM", parent="vm1"),))
    assert Code.PARENT_CYCLE in codes(project)


def test_a_loop_of_parents_is_reported_on_every_node_in_it() -> None:
    project = Project(
        nodes=(
            Node("a", "nas", "A", parent="b"),
            Node("b", "nas", "B", parent="c"),
            Node("c", "nas", "C", parent="a"),
        )
    )
    cycle = [p.subject for p in validate(project) if p.code is Code.PARENT_CYCLE]
    assert cycle == ["a", "b", "c"]


def test_a_node_hanging_off_a_loop_does_not_hang_the_check() -> None:
    project = Project(
        nodes=(
            Node("a", "nas", "A", parent="b"),
            Node("b", "nas", "B", parent="a"),
            Node("leaf", "vm", "Leaf", parent="a"),
        )
    )
    cycle = [p.subject for p in validate(project) if p.code is Code.PARENT_CYCLE]
    assert cycle == ["a", "b"]


# -------------------------------------------------------------------------- the grid


def test_two_nodes_on_one_cell_are_reported() -> None:
    project = Project(nodes=(Node("a", "nas", "A"), Node("b", "nas", "B")))
    problems = validate(project)
    assert [p.code for p in problems] == [Code.CELL_TAKEN]
    assert problems[0].subject == "b"


def test_the_same_cell_inside_different_parents_is_fine() -> None:
    project = Project(
        nodes=(
            Node("n1", "nas", "N1"),
            Node("n2", "nas", "N2", x=1),
            Node("v1", "vm", "V1", parent="n1"),
            Node("v2", "vm", "V2", parent="n2"),
        )
    )
    assert validate(project) == []


# ------------------------------------------------------------------------------ links


def two_hosts() -> tuple[Node, Node]:
    return new_node("switch", "Switch", []), new_node("nas", "NAS", ["switch"], x=1)


def test_a_cable_between_existing_interfaces_is_fine() -> None:
    switch, nas = two_hosts()
    link = cable("l1", ("switch", "port1"), ("nas", "eth1"))
    assert validate(Project(nodes=(switch, nas), links=(link,))) == []


def test_a_cable_to_a_missing_node_is_reported() -> None:
    switch, _ = two_hosts()
    link = cable("l1", ("switch", "port1"), ("ghost", "eth1"))
    assert codes(Project(nodes=(switch,), links=(link,))) == [Code.LINK_ENDPOINT]


def test_a_cable_to_a_missing_port_is_reported() -> None:
    switch, nas = two_hosts()
    link = cable("l1", ("switch", "port9"), ("nas", "eth1"))
    assert codes(Project(nodes=(switch, nas), links=(link,))) == [Code.LINK_ENDPOINT]


def test_a_cable_from_a_node_to_itself_is_reported() -> None:
    switch, _ = two_hosts()
    link = cable("l1", ("switch", "port1"), ("switch", "port2"))
    assert codes(Project(nodes=(switch,), links=(link,))) == [Code.LINK_TO_SELF]


def test_the_ninth_cable_on_an_eight_port_switch_cannot_find_a_port() -> None:
    switch = new_node("switch", "Switch", [])
    hosts = [new_node("workstation", f"PC {n}", ["switch"], x=n + 1) for n in range(9)]
    links = [
        cable(f"l{n}", ("switch", f"port{n + 1}"), (host.id, "eth1"))
        for n, host in enumerate(hosts)
    ]
    # Nine hosts, and the ninth is cabled to a port the switch does not have.
    problems = validate(Project(nodes=(switch, *hosts), links=tuple(links)))
    assert [p.code for p in problems] == [Code.LINK_ENDPOINT]
    assert problems[0].subject == "l8"


def test_two_cables_on_one_port_are_reported() -> None:
    switch = new_node("switch", "Switch", [])
    pcs = [new_node("workstation", f"PC {n}", ["switch"], x=n + 1) for n in range(2)]
    links = (
        cable("l0", ("switch", "port1"), (pcs[0].id, "eth1")),
        cable("l1", ("switch", "port1"), (pcs[1].id, "eth1")),
    )
    problems = validate(Project(nodes=(switch, *pcs), links=links))
    assert [(p.code, p.subject) for p in problems] == [(Code.PORT_BUSY, "switch:port1")]


def test_many_wireless_clients_may_share_an_access_point_interface() -> None:
    ap = Node("ap", "access_point", "AP", interfaces=(Interface("wlan0"),))
    phones = [new_node("iot", f"Phone {n}", ["ap"], x=n + 1) for n in range(3)]
    links = tuple(
        cable(f"l{n}", ("ap", "wlan0"), (phone.id, "eth1"), medium=Medium.WIFI)
        for n, phone in enumerate(phones)
    )
    assert validate(Project(nodes=(ap, *phones), links=links)) == []


def test_a_cable_and_a_wireless_link_cannot_share_an_interface() -> None:
    ap = Node("ap", "access_point", "AP", interfaces=(Interface("eth1"),))
    switch = new_node("switch", "Switch", ["ap"], x=1)
    phone = new_node("iot", "Phone", ["ap", "switch"], x=2)
    links = (
        cable("wired", ("ap", "eth1"), ("switch", "port1")),
        cable("radio", ("ap", "eth1"), (phone.id, "eth1"), medium=Medium.WIFI),
    )
    assert codes(Project(nodes=(ap, switch, phone), links=links)) == [Code.PORT_BUSY]


def test_two_interfaces_with_the_same_name_are_reported() -> None:
    node = Node("nas", "nas", "NAS", interfaces=(Interface("eth1"), Interface("eth1")))
    assert codes(Project(nodes=(node,))) == [Code.DUPLICATE_INTERFACE]


# ----------------------------------------------------------------------------- rules


def test_a_rule_on_a_device_that_does_not_forward_is_reported() -> None:
    node = Node("sw", "switch", "Switch", rules=(Rule(RuleAction.DENY),))
    assert codes(Project(nodes=(node,))) == [Code.RULE_ON_NON_ROUTER]


def test_a_virtual_machine_that_routes_may_carry_rules() -> None:
    node = Node("fw", "vm", "OPNsense", routes=True, rules=(Rule(RuleAction.DENY),))
    assert validate(Project(nodes=(node,))) == []


def test_a_rule_that_names_a_missing_node_is_reported() -> None:
    gateway = Node("gw", "firewall", "GW", rules=(Rule(RuleAction.ALLOW, "ghost", "10.0.0.0/8"),))
    assert codes(Project(nodes=(gateway,))) == [Code.RULE_REFERENCE]


# ----------------------------------------------------------------------------- flows


def test_a_flow_between_existing_nodes_is_fine() -> None:
    project = Project(
        nodes=(Node("a", "workstation", "A"), Node("b", "nas", "B", x=1)),
        flows=(Flow("f1", "a", "b", 443),),
    )
    assert validate(project) == []


def test_a_flow_to_a_missing_node_is_reported() -> None:
    project = Project(
        nodes=(Node("a", "workstation", "A"),), flows=(Flow("f1", "a", "ghost", 443),)
    )
    assert codes(project) == [Code.FLOW_ENDPOINT]


def test_a_flow_to_itself_is_reported() -> None:
    project = Project(nodes=(Node("a", "workstation", "A"),), flows=(Flow("f1", "a", "a", 443),))
    assert codes(project) == [Code.FLOW_TO_SELF]


# ----------------------------------------------------------------------------- order


def test_problems_come_out_in_a_stable_order() -> None:
    project = Project(
        nodes=(
            Node("z", "toaster", "Z"),
            Node("a", "toaster", "A", x=1),
            Node("m", "vm", "M", x=2, parent="ghost"),
        )
    )
    subjects = [p.subject for p in validate(project)]
    assert subjects == sorted(subjects)
    assert validate(project) == validate(project)
