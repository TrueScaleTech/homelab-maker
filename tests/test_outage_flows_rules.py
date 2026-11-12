"""Switching things off, and the operations that write flows, services and rules."""

import pytest

from homelab_maker.model import Project, Protocol, Rule, RuleAction, Service
from homelab_maker.operations import (
    add_flow,
    add_node,
    add_rule,
    add_service,
    connect,
    move_rule,
    remove_flows,
    remove_rule,
    remove_service,
    replace_rule,
    replace_service,
)
from homelab_maker.outage import what_goes_down, with_descendants, without
from homelab_maker.reachability import Reason, analyse_all
from homelab_maker.validation import validate

# ------------------------------------------------------------------------- outages


def test_switching_off_the_switch_breaks_the_flows_that_cross_it(sample: Project) -> None:
    outage = what_goes_down(sample, ["switch"])
    assert {r.flow for r in outage.broken} == {
        "desktop-nas-ui",
        "laptop-dashboard",
        "laptop-files",
    }
    assert not outage.harmless
    assert set(outage.cut_off) == {"ap", "camera", "desktop", "laptop", "nas"}
    assert outage.stopped == ("switch",)


def test_a_flow_that_already_failed_is_not_counted_as_broken(sample: Project) -> None:
    assert "camera-recordings" not in {r.flow for r in what_goes_down(sample, ["switch"]).broken}


def test_switching_off_a_host_takes_what_is_inside_it(sample: Project) -> None:
    outage = what_goes_down(sample, ["nas"])
    assert set(outage.stopped) == {
        "nas",
        "docker-host",
        "home-assistant",
        "nextcloud",
        "vaultwarden",
    }
    broken = {r.flow: r for r in outage.broken}
    assert set(broken) == {"desktop-nas-ui", "laptop-dashboard", "laptop-files"}
    assert broken["desktop-nas-ui"].reason is Reason.MISSING
    assert broken["desktop-nas-ui"].detail == "TrueNAS is switched off"
    assert broken["desktop-nas-ui"].stopped_at == "nas"


def test_switching_off_a_guest_leaves_its_host_and_the_rest_running(sample: Project) -> None:
    outage = what_goes_down(sample, ["home-assistant"])
    assert {r.flow for r in outage.broken} == {"laptop-dashboard"}
    assert outage.cut_off == ()


def test_switching_off_a_leaf_breaks_nothing_else(sample: Project) -> None:
    outage = what_goes_down(sample, ["camera"])
    assert outage.harmless and outage.broken == () and outage.cut_off == ()


def test_the_modem_cuts_the_whole_house_from_the_internet(sample: Project) -> None:
    outage = what_goes_down(sample, ["modem"])
    assert "gateway" in outage.cut_off and "switch" in outage.cut_off
    assert outage.broken == ()  # none of the four flows needs the Internet


def test_switching_off_the_internet_has_nobody_to_measure_against(sample: Project) -> None:
    outage = what_goes_down(sample, ["internet"])
    assert outage.stopped == ("internet",)
    assert outage.cut_off == ()


def test_everything_off_is_handled() -> None:
    project, _ = add_node(Project(), "nas", 0, 0)
    outage = what_goes_down(project, ["nas"])
    assert outage.cut_off == () and outage.broken == ()
    assert what_goes_down(Project(), []).harmless


def test_without_an_internet_the_biggest_group_is_the_reference() -> None:
    project = Project()
    for index, kind in enumerate(["switch", "nas", "server", "printer"]):
        project, _ = add_node(project, kind, index * 2, 0)
    for first, second in [("switch", "nas"), ("switch", "server-or-mini-pc"), ("nas", "printer")]:
        project, _ = connect(project, first, second)
    assert what_goes_down(project, ["nas"]).cut_off == ("printer",)


def test_the_project_itself_is_not_changed(sample: Project) -> None:
    before = sample
    what_goes_down(sample, ["switch"])
    assert sample == before


def test_without_removes_cables_to_the_stopped_devices(sample: Project) -> None:
    reduced = without(sample, ["switch"])
    assert reduced.node("switch") is None
    assert all("switch" not in (link.a.node, link.b.node) for link in reduced.links)
    assert validate(reduced) == []


def test_descendants_are_collected_at_every_depth(sample: Project) -> None:
    assert with_descendants(sample, ["docker-host"]) == {"docker-host", "nextcloud", "vaultwarden"}


# --------------------------------------------------------------------------- flows


def two() -> Project:
    project, _ = add_node(Project(), "workstation", 0, 0)
    project, _ = add_node(project, "nas", 4, 0)
    return project


def test_a_flow_is_added_with_an_id_from_its_ends_and_port() -> None:
    project, flow_id = add_flow(two(), "desktop-or-laptop", "nas", 443, Protocol.TCP, " Web UI ")
    assert flow_id == "desktop-or-laptop-nas-443"
    assert project.flows[0].description == "Web UI"
    project, second = add_flow(project, "desktop-or-laptop", "nas", 443)
    assert second == "desktop-or-laptop-nas-443-2"
    assert validate(project) == []


def test_a_flow_needs_two_different_devices_that_exist() -> None:
    with pytest.raises(ValueError, match="there is no node 'ghost'"):
        add_flow(two(), "ghost", "nas", 443)
    with pytest.raises(ValueError, match="there is no node 'ghost'"):
        add_flow(two(), "nas", "ghost", 443)
    with pytest.raises(ValueError, match="to itself"):
        add_flow(two(), "nas", "nas", 443)
    with pytest.raises(ValueError, match="between 1 and 65535"):
        add_flow(two(), "desktop-or-laptop", "nas", 70000)


def test_flows_are_removed_by_id() -> None:
    project, flow_id = add_flow(two(), "desktop-or-laptop", "nas", 443)
    assert remove_flows(project, [flow_id]).flows == ()
    with pytest.raises(ValueError, match="there is no flow 'nope'"):
        remove_flows(project, ["nope"])


# ------------------------------------------------------------------------- services


def test_a_service_is_added_and_a_duplicate_port_is_refused() -> None:
    project = add_service(two(), "nas", "Web UI", 443)
    assert project.node("nas").services == (Service("Web UI", 443),)  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="already listens on tcp/443"):
        add_service(project, "nas", "Other", 443)
    project = add_service(project, "nas", "Discovery", 443, Protocol.UDP)  # another protocol
    assert len(project.node("nas").services) == 2  # type: ignore[union-attr]


def test_a_service_is_removed_by_position() -> None:
    project = add_service(add_service(two(), "nas", "A", 1), "nas", "B", 2)
    project = remove_service(project, "nas", 0)
    assert [s.name for s in project.node("nas").services] == ["B"]  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="no service number 3"):
        remove_service(project, "nas", 2)
    with pytest.raises(ValueError, match="there is no node"):
        remove_service(project, "ghost", 0)


def test_a_service_is_replaced_without_clashing_with_its_neighbours() -> None:
    project = add_service(add_service(two(), "nas", "A", 1), "nas", "B", 2)
    changed = replace_service(project, "nas", 0, Service("A", 1, Protocol.UDP))
    assert changed.node("nas").services[0].protocol is Protocol.UDP  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="already listens on tcp/2"):
        replace_service(project, "nas", 0, Service("A", 2))
    with pytest.raises(ValueError, match="no service number 5"):
        replace_service(project, "nas", 4, Service("A", 3))
    with pytest.raises(ValueError, match="there is no node"):
        replace_service(project, "ghost", 0, Service("A", 3))
    with pytest.raises(ValueError, match="there is no node"):
        add_service(project, "ghost", "A", 3)


# ---------------------------------------------------------------------------- rules


def firewalled() -> Project:
    project, _ = add_node(Project(), "firewall", 0, 0)
    project, _ = add_node(project, "nas", 4, 0)
    return project


def test_rules_are_added_in_order_and_move_up_and_down() -> None:
    first, second = Rule(RuleAction.ALLOW, port=None), Rule(RuleAction.DENY, source="nas")
    project = add_rule(add_rule(firewalled(), "firewall", first), "firewall", second)
    assert project.node("firewall").rules == (first, second)  # type: ignore[union-attr]
    project = move_rule(project, "firewall", 1, -1)
    assert project.node("firewall").rules == (second, first)  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="cannot move any further"):
        move_rule(project, "firewall", 0, -1)
    with pytest.raises(ValueError, match="cannot move any further"):
        move_rule(project, "firewall", 1, 1)
    assert validate(project) == []


def test_rules_can_be_replaced_and_removed() -> None:
    project = add_rule(firewalled(), "firewall", Rule(RuleAction.ALLOW))
    project = replace_rule(project, "firewall", 0, Rule(RuleAction.DENY))
    assert project.node("firewall").rules[0].action is RuleAction.DENY  # type: ignore[union-attr]
    assert remove_rule(project, "firewall", 0).node("firewall").rules == ()  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="no rule number 2"):
        remove_rule(project, "firewall", 1)
    with pytest.raises(ValueError, match="no rule number 2"):
        replace_rule(project, "firewall", 1, Rule(RuleAction.ALLOW))


def test_a_device_that_does_not_route_takes_no_rules() -> None:
    with pytest.raises(ValueError, match="does not route traffic"):
        add_rule(two(), "nas", Rule(RuleAction.ALLOW))
    with pytest.raises(ValueError, match="there is no node"):
        add_rule(two(), "ghost", Rule(RuleAction.ALLOW))


def test_a_rule_cannot_name_a_device_that_is_not_there() -> None:
    with pytest.raises(ValueError, match="there is no such device"):
        add_rule(firewalled(), "firewall", Rule(RuleAction.ALLOW, destination="ghost"))
    project = add_rule(firewalled(), "firewall", Rule(RuleAction.ALLOW, destination="10.0.0.0/8"))
    with pytest.raises(ValueError, match="there is no such device"):
        replace_rule(project, "firewall", 0, Rule(RuleAction.ALLOW, source="ghost"))


def test_adding_a_flow_and_a_rule_changes_the_answer() -> None:
    project, _ = add_node(Project(), "workstation", 0, 0)
    project, _ = add_node(project, "firewall", 2, 0)
    project, _ = add_node(project, "nas", 4, 0)
    project, _ = connect(project, "desktop-or-laptop", "firewall")
    project, _ = connect(project, "firewall", "nas")
    project, _ = add_flow(project, "desktop-or-laptop", "nas", 443)
    assert analyse_all(project)[0].reachable
    project = add_rule(project, "firewall", Rule(RuleAction.DENY, destination="nas"))
    assert not analyse_all(project)[0].reachable
