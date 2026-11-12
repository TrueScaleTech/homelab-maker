"""Design checks: legal homelabs that are probably not what was meant."""

from dataclasses import replace

from homelab_maker.checks import Check, Finding, Severity, run_checks, vlan_problem
from homelab_maker.model import Interface, InterfaceMode, Medium, Project
from homelab_maker.operations import (
    add_node,
    connect,
    set_addresses,
    set_mode,
    set_trunk_vlans,
    set_vlan,
)


def kinds(findings: list[Finding]) -> list[Check]:
    return [f.check for f in findings]


def two_devices(*, first: str = "switch", second: str = "nas") -> Project:
    project, _ = add_node(Project(), first, 0, 0)
    project, _ = add_node(project, second, 4, 0)
    return project


def test_the_shipped_example_has_no_warnings(sample: Project) -> None:
    assert [f for f in run_checks(sample) if f.severity is Severity.WARNING] == []


def test_an_empty_project_has_nothing_to_report() -> None:
    assert run_checks(Project()) == []


# ------------------------------------------------------------------------- addresses


def test_one_address_on_two_devices_is_reported() -> None:
    project = two_devices()
    project = set_addresses(project, "switch", "port1", ["192.168.1.5/24"])
    project = set_addresses(project, "nas", "eth1", ["192.168.1.5/24"])
    found = [f for f in run_checks(project) if f.check is Check.DUPLICATE_ADDRESS]
    assert len(found) == 1
    assert "192.168.1.5" in found[0].message
    assert set(found[0].nodes) == {"switch", "nas"}


def test_the_same_host_address_with_another_prefix_still_clashes() -> None:
    project = two_devices()
    project = set_addresses(project, "switch", "port1", ["192.168.1.5/24"])
    project = set_addresses(project, "nas", "eth1", ["192.168.1.5/16"])
    assert Check.DUPLICATE_ADDRESS in kinds(run_checks(project))


def test_different_addresses_do_not_clash() -> None:
    project = two_devices()
    project = set_addresses(project, "switch", "port1", ["192.168.1.5/24"])
    project = set_addresses(project, "nas", "eth1", ["192.168.1.6/24"])
    assert Check.DUPLICATE_ADDRESS not in kinds(run_checks(project))


# --------------------------------------------------------------------------- VLANs


def joined(project: Project) -> Project:
    project, _ = connect(project, "switch", "nas")
    return project


def test_two_access_ports_on_different_vlans_are_reported() -> None:
    project = joined(two_devices())
    project = set_vlan(project, "switch", "port1", 10)
    project = set_vlan(project, "nas", "eth1", 20)
    found = [f for f in run_checks(project) if f.check is Check.VLAN_MISMATCH]
    assert len(found) == 1
    assert (
        "untagged VLAN" in found[0].message
        and "10" in found[0].message
        and "20" in found[0].message
    )


def test_two_access_ports_on_the_same_vlan_agree() -> None:
    project = joined(two_devices())
    project = set_vlan(project, "switch", "port1", 10)
    project = set_vlan(project, "nas", "eth1", 10)
    assert Check.VLAN_MISMATCH not in kinds(run_checks(project))


def test_no_vlan_means_the_default_vlan_on_both_sides() -> None:
    assert Check.VLAN_MISMATCH not in kinds(run_checks(joined(two_devices())))
    project = set_vlan(joined(two_devices()), "switch", "port1", 1)
    assert Check.VLAN_MISMATCH not in kinds(run_checks(project))


def test_an_access_port_against_a_trunk_with_another_native_vlan_is_reported() -> None:
    project = joined(two_devices())
    project = set_mode(project, "switch", "port1", InterfaceMode.TRUNK)
    project = set_vlan(project, "switch", "port1", 99)
    assert Check.VLAN_MISMATCH in kinds(run_checks(project))


def test_a_trunk_that_carries_a_vlan_the_other_end_does_not_is_reported() -> None:
    project, _ = add_node(Project(), "switch", 0, 0)
    project, _ = add_node(project, "switch", 4, 0)
    project, _ = connect(project, "switch", "switch-2")
    for node in ("switch", "switch-2"):
        project = set_mode(project, node, "port1", InterfaceMode.TRUNK)
    project = set_trunk_vlans(project, "switch", "port1", [10, 20])
    project = set_trunk_vlans(project, "switch-2", "port1", [10])
    found = [f for f in run_checks(project) if f.check is Check.VLAN_MISMATCH]
    assert len(found) == 1 and "20 is on one side only" in found[0].message
    project = set_trunk_vlans(project, "switch-2", "port1", [20, 10])
    assert Check.VLAN_MISMATCH not in kinds(run_checks(project))


def test_a_tunnel_has_no_vlans_to_compare() -> None:
    project = two_devices(first="server", second="firewall")
    project, _ = connect(project, "server-or-mini-pc", "firewall", Medium.VPN)
    project = set_vlan(project, "server-or-mini-pc", "tun0", 10)
    assert Check.VLAN_MISMATCH not in kinds(run_checks(project))


def test_vlan_problem_explains_itself() -> None:
    a = Interface("a", vlan=10)
    b = Interface("b", vlan=20)
    assert vlan_problem(a, a) is None
    assert vlan_problem(a, b) is not None


# ---------------------------------------------------------------------------- subnets


def test_joined_ports_in_different_networks_are_reported() -> None:
    project = joined(two_devices())
    project = set_addresses(project, "switch", "port1", ["192.168.1.2/24"])
    project = set_addresses(project, "nas", "eth1", ["10.0.0.2/24"])
    assert Check.SUBNET_MISMATCH in kinds(run_checks(project))


def test_joined_ports_in_one_network_agree() -> None:
    project = joined(two_devices())
    project = set_addresses(project, "switch", "port1", ["192.168.1.2/24"])
    project = set_addresses(project, "nas", "eth1", ["192.168.1.3/24", "10.0.0.2/24"])
    assert Check.SUBNET_MISMATCH not in kinds(run_checks(project))


def test_a_port_without_an_address_is_not_compared() -> None:
    project = joined(two_devices())
    project = set_addresses(project, "nas", "eth1", ["10.0.0.2/24"])
    assert Check.SUBNET_MISMATCH not in kinds(run_checks(project))


# --------------------------------------------------------------------------- others


def test_a_device_with_no_cable_is_reported() -> None:
    found = [f for f in run_checks(two_devices()) if f.check is Check.UNCONNECTED]
    assert {f.nodes[0] for f in found} == {"switch", "nas"}


def test_a_guest_does_not_need_a_cable_of_its_own() -> None:
    project, _ = add_node(Project(), "nas", 0, 0)
    project, _ = add_node(project, "vm", 0, 0, parent="nas")
    messages = [f.message for f in run_checks(project) if f.check is Check.UNCONNECTED]
    assert len(messages) == 1 and "NAS" in messages[0]


def test_a_cabled_router_port_without_an_address_is_reported() -> None:
    project = two_devices(first="firewall", second="switch")
    project, _ = connect(project, "firewall", "switch")
    found = [f for f in run_checks(project) if f.check is Check.NO_ADDRESS]
    assert len(found) == 1 and found[0].severity is Severity.WARNING and "eth1" in found[0].message


def test_a_cabled_endpoint_without_any_address_is_mentioned_but_not_a_warning() -> None:
    project = joined(two_devices())
    found = [f for f in run_checks(project) if f.check is Check.NO_ADDRESS]
    assert [f.severity for f in found] == [Severity.INFO]
    project = set_addresses(project, "nas", "eth1", ["10.0.0.2/24"])
    assert Check.NO_ADDRESS not in kinds(run_checks(project))


def test_the_internet_is_never_asked_for_an_address() -> None:
    project = two_devices(first="internet", second="modem")
    project, _ = connect(project, "internet", "modem-or-ont")
    assert Check.NO_ADDRESS not in kinds(run_checks(project))


def chain() -> Project:
    project = Project()
    for index, kind in enumerate(["internet", "router", "switch", "nas"]):
        project, _ = add_node(project, kind, index * 2, 0)
    for first, second in [("internet", "router"), ("router", "switch"), ("switch", "nas")]:
        project, _ = connect(project, first, second)
    return project


def test_a_switch_that_is_the_only_way_to_the_internet_is_a_single_point_of_failure() -> None:
    found = [f for f in run_checks(chain()) if f.check is Check.SINGLE_POINT_OF_FAILURE]
    by_first = {f.nodes[0]: f for f in found}
    assert set(by_first) == {"router", "switch"}
    assert by_first["switch"].nodes == ("switch", "nas")
    assert "loses the connection to Internet" in by_first["switch"].message
    assert by_first["switch"].severity is Severity.INFO


def test_a_second_path_removes_the_single_point_of_failure() -> None:
    project, _ = connect(chain(), "router", "nas")  # now the NAS has a way round the switch
    firsts = {f.nodes[0] for f in run_checks(project) if f.check is Check.SINGLE_POINT_OF_FAILURE}
    assert firsts == {"router"}


def test_without_an_internet_a_device_that_splits_the_network_is_reported() -> None:
    project = Project()
    for index, kind in enumerate(["switch", "nas", "server", "printer"]):
        project, _ = add_node(project, kind, index * 2, 0)
    for first, second in [("switch", "nas"), ("switch", "server-or-mini-pc"), ("nas", "printer")]:
        project, _ = connect(project, first, second)
    found = {f.nodes[0]: f for f in run_checks(project) if f.check is Check.SINGLE_POINT_OF_FAILURE}
    assert set(found) == {"nas", "switch"}  # either one splits the network
    assert found["nas"].nodes == ("nas", "printer")
    assert found["nas"].message.endswith("Printer loses the connection to the rest of the network")


def test_tiny_projects_have_no_single_point_of_failure_to_speak_of() -> None:
    project = joined(two_devices())
    assert Check.SINGLE_POINT_OF_FAILURE not in kinds(run_checks(project))


def test_warnings_come_before_information() -> None:
    findings = run_checks(chain())
    severities = [f.severity for f in findings]
    assert severities == sorted(severities, key=lambda s: s is Severity.INFO)


def test_a_broken_link_does_not_crash_the_checks() -> None:
    project = joined(two_devices())
    broken = replace(project, nodes=tuple(n for n in project.nodes if n.id != "nas"))
    run_checks(broken)
