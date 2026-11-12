"""Can A reach B, along which path, and what stops it: each rule of the analysis, on its own."""

from dataclasses import replace

from homelab_maker.model import (
    Flow,
    InterfaceMode,
    Medium,
    Project,
    Protocol,
    Rule,
    RuleAction,
    RuleProtocol,
)
from homelab_maker.operations import (
    add_flow,
    add_node,
    add_rule,
    add_service,
    connect,
    set_addresses,
    set_mode,
    set_trunk_vlans,
    set_vlan,
)
from homelab_maker.reachability import (
    NOT_MODELLED,
    Reason,
    Result,
    Verdict,
    analyse_all,
    analyse_flow,
    describe_rule,
)


def lab(*kinds: str) -> Project:
    """Devices in a row, named after their kind, with no cables."""
    project = Project()
    for index, kind in enumerate(kinds):
        project, _ = add_node(project, kind, index * 2, 0)
    return project


def cable(project: Project, first: str, second: str, **kwargs: object) -> Project:
    project, _ = connect(project, first, second, **kwargs)  # type: ignore[arg-type]
    return project


def ask(project: Project, source: str, destination: str, port: int = 443) -> Result:
    flow = Flow("f", source, destination, port)
    return analyse_flow(project, flow)


# ------------------------------------------------------------------------- the basics


def test_two_devices_on_one_switch_reach_each_other() -> None:
    project = lab("workstation", "switch", "nas")
    project = cable(project, "desktop-or-laptop", "switch")
    project = cable(project, "switch", "nas")
    result = ask(project, "desktop-or-laptop", "nas")
    assert result.verdict is Verdict.REACHABLE and result.reachable
    assert result.path == ("desktop-or-laptop", "switch", "nas")
    assert len(result.links) == 2 and all(result.links)
    assert result.detail == "via Desktop or laptop → Switch → NAS"
    assert result.reason is None and result.stopped_at is None


def test_without_a_cable_nothing_reaches_anything() -> None:
    result = ask(lab("workstation", "nas"), "desktop-or-laptop", "nas")
    assert result.verdict is Verdict.BLOCKED and result.reason is Reason.NO_PATH
    assert "no chain of cables" in result.detail
    assert result.path == ()


def test_a_device_in_the_middle_does_not_forward_traffic() -> None:
    project = lab("workstation", "nas", "server")
    project = cable(project, "desktop-or-laptop", "nas")
    project = cable(project, "nas", "server-or-mini-pc")
    result = ask(project, "desktop-or-laptop", "server-or-mini-pc")
    assert result.reason is Reason.NO_PATH


def test_a_router_in_the_middle_does_forward_it() -> None:
    project = lab("workstation", "router", "server")
    project = cable(project, "desktop-or-laptop", "router")
    project = cable(project, "router", "server-or-mini-pc")
    assert ask(project, "desktop-or-laptop", "server-or-mini-pc").reachable


def test_a_flow_with_a_missing_end_says_so() -> None:
    result = ask(lab("nas"), "nas", "ghost")
    assert result.reason is Reason.MISSING and "'ghost'" in result.detail
    assert ask(lab("nas"), "ghost", "nas").reason is Reason.MISSING


# ---------------------------------------------------------------------------- VLANs


def two_on_a_switch(first_vlan: int | None, second_vlan: int | None) -> Project:
    project = lab("workstation", "switch", "nas")
    project = cable(project, "desktop-or-laptop", "switch")
    project = cable(project, "switch", "nas")
    project = set_vlan(project, "desktop-or-laptop", "eth1", first_vlan)
    project = set_vlan(project, "switch", "port1", first_vlan)
    project = set_vlan(project, "switch", "port2", second_vlan)
    return set_vlan(project, "nas", "eth1", second_vlan)


def test_the_same_vlan_on_both_sides_of_a_switch_is_fine() -> None:
    assert ask(two_on_a_switch(10, 10), "desktop-or-laptop", "nas").reachable


def test_a_switch_does_not_carry_traffic_between_two_vlans() -> None:
    result = ask(two_on_a_switch(10, 20), "desktop-or-laptop", "nas")
    assert result.reason is Reason.VLAN
    assert "VLAN 10 cannot leave Switch through port2" in result.detail
    assert result.stopped_at == "switch"
    assert result.path == ("desktop-or-laptop", "switch", "nas")


def test_joined_ports_on_different_vlans_are_reported_at_the_link() -> None:
    project = lab("workstation", "nas")
    project = cable(project, "desktop-or-laptop", "nas")
    project = set_vlan(project, "desktop-or-laptop", "eth1", 10)
    project = set_vlan(project, "nas", "eth1", 20)
    result = ask(project, "desktop-or-laptop", "nas")
    assert result.reason is Reason.VLAN and "share no VLAN" in result.detail
    assert result.stopped_at == project.links[0].id


def test_no_vlan_on_either_side_is_the_default_vlan() -> None:
    project = cable(lab("workstation", "nas"), "desktop-or-laptop", "nas")
    assert ask(project, "desktop-or-laptop", "nas").reachable
    project = set_vlan(project, "nas", "eth1", 1)
    assert ask(project, "desktop-or-laptop", "nas").reachable


def trunked() -> Project:
    """A workstation and a NAS on VLAN 10, on two switches joined by a trunk."""
    project = lab("workstation", "switch", "nas")
    project, _ = add_node(project, "switch", 6, 0)
    project = cable(project, "desktop-or-laptop", "switch")
    project = cable(project, "switch", "switch-2")
    project = cable(project, "switch-2", "nas")
    for node, port in (
        ("desktop-or-laptop", "eth1"),
        ("switch", "port1"),
        ("switch-2", "port2"),
        ("nas", "eth1"),
    ):
        project = set_vlan(project, node, port, 10)
    for node in ("switch", "switch-2"):
        project = set_mode(
            project, node, "port2" if node == "switch" else "port1", InterfaceMode.TRUNK
        )
        project = set_vlan(project, node, "port2" if node == "switch" else "port1", 99)
    return project


def test_a_vlan_crosses_a_trunk_that_carries_it_tagged() -> None:
    project = trunked()
    project = set_trunk_vlans(project, "switch", "port2", [10])
    project = set_trunk_vlans(project, "switch-2", "port1", [10])
    assert ask(project, "desktop-or-laptop", "nas").reachable


def test_a_vlan_does_not_cross_a_trunk_that_does_not_carry_it() -> None:
    result = ask(trunked(), "desktop-or-laptop", "nas")
    assert result.reason is Reason.VLAN
    assert "VLAN 10 cannot leave Switch through port2" in result.detail


def test_a_router_moves_traffic_between_vlans() -> None:
    project = lab("workstation", "router", "nas")
    project = cable(project, "desktop-or-laptop", "router")
    project = cable(project, "router", "nas")
    project = set_vlan(project, "desktop-or-laptop", "eth1", 10)
    project = set_vlan(project, "router", "eth1", 10)
    project = set_vlan(project, "router", "eth2", 20)
    project = set_vlan(project, "nas", "eth1", 20)
    result = ask(project, "desktop-or-laptop", "nas")
    assert result.reachable and result.path == ("desktop-or-laptop", "router", "nas")


def test_a_tunnel_ignores_vlans() -> None:
    project = lab("server", "firewall")
    project = cable(project, "server-or-mini-pc", "firewall", medium=Medium.VPN)
    project = set_vlan(project, "server-or-mini-pc", "tun0", 10)
    project = set_vlan(project, "firewall", "tun0", 20)
    assert ask(project, "server-or-mini-pc", "firewall").reachable


# ----------------------------------------------------------------------------- rules


def gateway(*rules: Rule) -> Project:
    project = lab("workstation", "firewall", "nas")
    project = cable(project, "desktop-or-laptop", "firewall")
    project = cable(project, "firewall", "nas")
    for rule in rules:
        project = add_rule(project, "firewall", rule)
    return project


def test_a_router_with_no_rules_lets_everything_through() -> None:
    assert ask(gateway(), "desktop-or-laptop", "nas").reachable


def test_a_deny_rule_stops_the_flow_and_names_the_rule() -> None:
    project = gateway(Rule(RuleAction.DENY))
    result = ask(project, "desktop-or-laptop", "nas")
    assert result.reason is Reason.RULE and result.stopped_at == "firewall"
    assert result.detail == "Firewall denies it with rule 1 (deny any from any to any)"
    assert result.path == ("desktop-or-laptop", "firewall", "nas")


def test_the_first_matching_rule_wins() -> None:
    allow = Rule(RuleAction.ALLOW, protocol=RuleProtocol.TCP, port=443)
    deny = Rule(RuleAction.DENY)
    assert ask(gateway(allow, deny), "desktop-or-laptop", "nas", 443).reachable
    assert not ask(gateway(deny, allow), "desktop-or-laptop", "nas", 443).reachable


def test_a_port_rule_only_matches_that_port_and_protocol() -> None:
    deny_ssh = Rule(RuleAction.DENY, protocol=RuleProtocol.TCP, port=22)
    project = gateway(deny_ssh)
    assert not ask(project, "desktop-or-laptop", "nas", 22).reachable
    assert ask(project, "desktop-or-laptop", "nas", 443).reachable
    udp = analyse_flow(project, Flow("f", "desktop-or-laptop", "nas", 22, Protocol.UDP))
    assert udp.reachable
    icmp = gateway(Rule(RuleAction.DENY, protocol=RuleProtocol.ICMP))
    assert analyse_flow(icmp, Flow("f", "desktop-or-laptop", "nas", 443)).reachable


def test_a_rule_can_name_a_network() -> None:
    project = set_addresses(gateway(), "desktop-or-laptop", "eth1", ["192.168.5.9/24"])
    denied = add_rule(project, "firewall", Rule(RuleAction.DENY, source="192.168.5.0/24"))
    assert not ask(denied, "desktop-or-laptop", "nas").reachable
    other = add_rule(project, "firewall", Rule(RuleAction.DENY, source="10.0.0.0/8"))
    assert ask(other, "desktop-or-laptop", "nas").reachable


def test_a_network_rule_cannot_match_a_device_with_no_address() -> None:
    project = add_rule(gateway(), "firewall", Rule(RuleAction.DENY, source="192.168.5.0/24"))
    assert ask(project, "desktop-or-laptop", "nas").reachable


def test_a_rule_can_name_a_device_and_covers_what_is_inside_it() -> None:
    project = lab("workstation", "firewall", "nas")
    project, _ = add_node(project, "vm", 0, 0, parent="nas")
    project = cable(project, "desktop-or-laptop", "firewall")
    project = cable(project, "firewall", "nas")
    project = add_rule(project, "firewall", Rule(RuleAction.DENY, destination="nas"))
    assert not ask(project, "desktop-or-laptop", "nas").reachable
    assert not ask(project, "desktop-or-laptop", "virtual-machine").reachable


def test_a_rule_on_another_device_does_not_apply() -> None:
    project = add_rule(gateway(), "firewall", Rule(RuleAction.DENY, source="nas"))
    assert ask(project, "desktop-or-laptop", "nas").reachable


def test_a_way_round_a_denying_firewall_is_found() -> None:
    project = lab("server", "firewall", "router", "nas")
    for first, second in [
        ("server-or-mini-pc", "firewall"),
        ("firewall", "nas"),
        ("server-or-mini-pc", "router"),
        ("router", "nas"),
    ]:
        project = cable(project, first, second)
    project = add_rule(project, "firewall", Rule(RuleAction.DENY))
    result = ask(project, "server-or-mini-pc", "nas")
    assert result.reachable and "Router" in result.detail


def test_describing_a_rule() -> None:
    rule = Rule(RuleAction.ALLOW, "10.0.0.0/8", "nas", RuleProtocol.TCP, 443)
    assert describe_rule(rule) == "allow tcp/443 from 10.0.0.0/8 to nas"


# --------------------------------------------------------------------------- services


def test_a_port_nothing_listens_on_is_blocked() -> None:
    project = cable(lab("workstation", "nas"), "desktop-or-laptop", "nas")
    project = add_service(project, "nas", "Web UI", 443)
    assert ask(project, "desktop-or-laptop", "nas", 443).reachable
    result = ask(project, "desktop-or-laptop", "nas", 8080)
    assert result.reason is Reason.NO_SERVICE and "tcp/8080" in result.detail
    assert result.stopped_at == "nas"
    udp = analyse_flow(project, Flow("f", "desktop-or-laptop", "nas", 443, Protocol.UDP))
    assert udp.reason is Reason.NO_SERVICE


def test_a_device_with_no_services_is_not_checked_but_says_so() -> None:
    project = cable(lab("workstation", "nas"), "desktop-or-laptop", "nas")
    result = ask(project, "desktop-or-laptop", "nas", 8080)
    assert result.reachable
    assert result.notes == ("NAS lists no services, so the port was not checked",)


# ----------------------------------------------------------------------------- guests


def hosted() -> Project:
    project = lab("workstation", "switch", "nas")
    project, _ = add_node(project, "vm", 0, 0, parent="nas")
    project, _ = add_node(project, "vm", 1, 0, parent="nas")
    project = cable(project, "desktop-or-laptop", "switch")
    return cable(project, "switch", "nas")


def test_a_guest_is_reached_through_its_host() -> None:
    result = ask(hosted(), "desktop-or-laptop", "virtual-machine")
    assert result.reachable
    assert result.path == ("desktop-or-laptop", "switch", "nas", "virtual-machine")
    assert result.links[-1] == ""  # the last step is no cable


def test_a_guest_reaches_the_network_through_its_host() -> None:
    result = ask(hosted(), "virtual-machine", "desktop-or-laptop")
    assert result.path == ("virtual-machine", "nas", "switch", "desktop-or-laptop")


def test_two_guests_of_one_host_reach_each_other_without_a_cable() -> None:
    result = ask(hosted(), "virtual-machine", "virtual-machine-2")
    assert result.reachable and result.path == ("virtual-machine", "nas", "virtual-machine-2")


def test_a_container_inside_a_vm_inside_a_host() -> None:
    project, _ = add_node(hosted(), "container", 0, 0, parent="virtual-machine")
    result = ask(project, "desktop-or-laptop", "container")
    assert result.path[-3:] == ("nas", "virtual-machine", "container")


def test_a_host_reaches_its_own_guest() -> None:
    result = ask(hosted(), "nas", "virtual-machine")
    assert result.reachable and result.path == ("nas", "virtual-machine")


def test_a_guest_on_its_own_vlan_follows_it_to_the_network() -> None:
    project = set_vlan(hosted(), "virtual-machine", "vnic1", 30)
    result = ask(project, "virtual-machine", "desktop-or-laptop")
    assert result.reason is Reason.VLAN  # the host's port is on the default VLAN
    project = set_vlan(project, "nas", "eth1", 30)
    project = set_vlan(project, "switch", "port2", 30)
    project = set_vlan(project, "switch", "port1", 30)
    project = set_vlan(project, "desktop-or-laptop", "eth1", 30)
    assert ask(project, "virtual-machine", "desktop-or-laptop").reachable


def test_a_guest_cannot_be_reached_on_a_vlan_it_is_not_on() -> None:
    project = set_vlan(hosted(), "virtual-machine", "vnic1", 30)
    result = ask(project, "desktop-or-laptop", "virtual-machine")
    assert not result.reachable


# --------------------------------------------------------------------------- the example


def test_the_example_answers_its_four_flows(sample: Project) -> None:
    results = {r.flow: r for r in analyse_all(sample)}
    assert results["desktop-nas-ui"].reachable
    assert results["laptop-files"].reachable
    assert results["laptop-dashboard"].reachable
    assert results["laptop-dashboard"].path[-2:] == ("nas", "home-assistant")
    camera = results["camera-recordings"]
    assert camera.reason is Reason.RULE and camera.stopped_at == "gateway"
    assert camera.detail.startswith("Gateway denies it with rule 1")


def test_taking_the_deny_rule_away_lets_the_camera_through(sample: Project) -> None:
    gateway = sample.node("gateway")
    assert gateway is not None
    freed = replace(
        sample,
        nodes=tuple(
            replace(n, rules=gateway.rules[1:]) if n.id == "gateway" else n for n in sample.nodes
        ),
    )
    assert {r.flow: r for r in analyse_all(freed)}["camera-recordings"].reachable


def test_a_flow_added_to_the_example_is_analysed(sample: Project) -> None:
    project, flow_id = add_flow(sample, "desktop", "home-assistant", 8123)
    result = next(r for r in analyse_all(project) if r.flow == flow_id)
    assert result.reachable


def test_the_list_of_what_is_not_modelled_is_not_empty() -> None:
    assert len(NOT_MODELLED) >= 5 and all(item for item in NOT_MODELLED)
