"""Design checks: warnings about the homelab, as opposed to errors in the model.

``validation`` refuses a project that contradicts itself (a cable to a device that does not
exist). These checks never refuse anything. They point at things that are legal but probably
not what was meant: two devices with one address, a cable between ports on different VLANs,
a switch whose failure strands half the house.

Like everything outside ``gui`` this knows nothing about the window.
"""

import ipaddress
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from homelab_maker.catalog import CATALOG, Category
from homelab_maker.model import (
    Interface,
    InterfaceMode,
    Link,
    Medium,
    Node,
    Project,
    node_routes,
)
from homelab_maker.viewmodel import shown_as

DEFAULT_VLAN = 1


class Severity(StrEnum):
    WARNING = "warning"
    INFO = "info"


class Check(StrEnum):
    DUPLICATE_ADDRESS = "duplicate-address"
    VLAN_MISMATCH = "vlan-mismatch"
    SUBNET_MISMATCH = "subnet-mismatch"
    UNCONNECTED = "unconnected"
    NO_ADDRESS = "no-address"
    SINGLE_POINT_OF_FAILURE = "single-point-of-failure"


@dataclass(frozen=True, slots=True)
class Finding:
    check: Check
    severity: Severity
    message: str
    # The devices to select to look at it, the most relevant first.
    nodes: tuple[str, ...]


def run_checks(project: Project) -> list[Finding]:
    """Every finding, in a stable order: warnings before information, then by text."""
    findings: list[Finding] = []
    findings += _duplicate_addresses(project)
    findings += _vlan_mismatches(project)
    findings += _subnet_mismatches(project)
    findings += _unconnected(project)
    findings += _missing_addresses(project)
    findings += _single_points_of_failure(project)
    order = {Severity.WARNING: 0, Severity.INFO: 1}
    return sorted(findings, key=lambda f: (order[f.severity], f.check.value, f.message))


# -------------------------------------------------------------------------- addresses


def _duplicate_addresses(project: Project) -> list[Finding]:
    owners: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for node in project.nodes:
        for interface in node.interfaces:
            for address in interface.addresses:
                host = str(ipaddress.ip_interface(address).ip)
                owners[host].append((node.id, interface.name))
    findings = []
    for host, where in sorted(owners.items()):
        if len(where) < 2:
            continue
        names = ", ".join(f"{_name(project, n)} ({i})" for n, i in where)
        findings.append(
            Finding(
                Check.DUPLICATE_ADDRESS,
                Severity.WARNING,
                f"{host} is used by more than one interface: {names}",
                tuple(dict.fromkeys(n for n, _ in where)),
            )
        )
    return findings


def _name(project: Project, node_id: str) -> str:
    node = project.node(node_id)
    return node.name if node else node_id


def _networks(interface: Interface) -> set[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    return {ipaddress.ip_interface(a).network for a in interface.addresses}


def _subnet_mismatches(project: Project) -> list[Finding]:
    findings = []
    for link in project.links:
        if link.medium is Medium.VPN:
            continue
        first, second = _interfaces_of(project, link)
        if first is None or second is None or not first[1].addresses or not second[1].addresses:
            continue
        if _networks(first[1]) & _networks(second[1]):
            continue
        findings.append(
            Finding(
                Check.SUBNET_MISMATCH,
                Severity.WARNING,
                f"{_name(project, first[0].id)} ({first[1].name}) and "
                f"{_name(project, second[0].id)} ({second[1].name}) are joined, "
                "but their addresses are in different networks",
                (first[0].id, second[0].id),
            )
        )
    return findings


def _interfaces_of(
    project: Project, link: Link
) -> tuple[tuple[Node, Interface] | None, tuple[Node, Interface] | None]:
    ends: list[tuple[Node, Interface] | None] = []
    for end in (link.a, link.b):
        node = project.node(end.node)
        found = (
            next((i for i in node.interfaces if i.name == end.interface), None) if node else None
        )
        ends.append((node, found) if node is not None and found is not None else None)
    return ends[0], ends[1]


def _missing_addresses(project: Project) -> list[Finding]:
    cabled: dict[str, set[str]] = defaultdict(set)
    for link in project.links:
        for end in (link.a, link.b):
            cabled[end.node].add(end.interface)
    findings = []
    for node in project.nodes:
        kind = CATALOG.get(node.kind)
        if kind is None or kind.category is Category.EXTERNAL or node.id not in cabled:
            continue
        if node_routes(node):
            bare = sorted(
                i.name for i in node.interfaces if i.name in cabled[node.id] and not i.addresses
            )
            if bare:
                findings.append(
                    Finding(
                        Check.NO_ADDRESS,
                        Severity.WARNING,
                        f"{node.name} routes traffic, but {', '.join(bare)} has a cable and "
                        "no address",
                        (node.id,),
                    )
                )
        elif not kind.carries and not any(i.addresses for i in node.interfaces):
            findings.append(
                Finding(
                    Check.NO_ADDRESS,
                    Severity.INFO,
                    f"{node.name} is cabled but has no address on any interface",
                    (node.id,),
                )
            )
    return findings


# ------------------------------------------------------------------------------ VLANs


def _membership(interface: Interface) -> tuple[int, frozenset[int]]:
    """The untagged VLAN of a port and the VLANs it carries tagged."""
    native = interface.vlan or DEFAULT_VLAN
    if interface.mode is InterfaceMode.TRUNK:
        return native, frozenset(interface.trunk_vlans)
    return native, frozenset()


def vlan_problem(first: Interface, second: Interface) -> str | None:
    """Why two ports joined by a cable do not agree on VLANs, or ``None`` when they do."""
    native_a, tagged_a = _membership(first)
    native_b, tagged_b = _membership(second)
    if native_a != native_b:
        return f"the untagged VLAN is {native_a} on one side and {native_b} on the other"
    if tagged_a != tagged_b:
        only = sorted(tagged_a ^ tagged_b)
        return (
            "the tagged VLANs differ (" + ", ".join(str(v) for v in only) + " is on one side only)"
        )
    return None


def _vlan_mismatches(project: Project) -> list[Finding]:
    findings = []
    for link in project.links:
        if link.medium is Medium.VPN:
            continue
        first, second = _interfaces_of(project, link)
        if first is None or second is None:
            continue
        problem = vlan_problem(first[1], second[1])
        if problem is None:
            continue
        findings.append(
            Finding(
                Check.VLAN_MISMATCH,
                Severity.WARNING,
                f"{_name(project, first[0].id)} ({first[1].name}) is joined to "
                f"{_name(project, second[0].id)} ({second[1].name}), but {problem}",
                (first[0].id, second[0].id),
            )
        )
    return findings


# --------------------------------------------------------------------- connectivity


def _unconnected(project: Project) -> list[Finding]:
    linked = {end.node for link in project.links for end in (link.a, link.b)}
    return [
        Finding(
            Check.UNCONNECTED,
            Severity.WARNING,
            f"{node.name} has no cable or link, so nothing can reach it",
            (node.id,),
        )
        for node in project.nodes
        if node.parent is None and node.id not in linked
    ]


def adjacency(project: Project) -> dict[str, set[str]]:
    """Which top-level devices are joined, counting a guest as its host."""
    graph: dict[str, set[str]] = {node.id: set() for node in project.children(None)}
    for link in project.links:
        a = shown_as(project, link.a.node, None)
        b = shown_as(project, link.b.node, None)
        if a is not None and b is not None and a != b:
            graph[a].add(b)
            graph[b].add(a)
    return graph


def _reach(graph: dict[str, set[str]], start: str, removed: str | None = None) -> set[str]:
    seen = {start}
    frontier = [start]
    while frontier:
        for neighbour in graph[frontier.pop()]:
            if neighbour != removed and neighbour not in seen:
                seen.add(neighbour)
                frontier.append(neighbour)
    return seen


def _components(graph: dict[str, set[str]], removed: str) -> list[set[str]]:
    """The groups of devices that stay joined when ``removed`` is taken away."""
    left = set(graph) - {removed}
    groups = []
    while left:
        group = _reach(graph, min(left), removed=removed)
        groups.append(group)
        left -= group
    return groups


def _single_points_of_failure(project: Project) -> list[Finding]:
    graph = adjacency(project)
    if len(graph) < 3:
        return []
    internet = next((n.id for n in project.children(None) if n.kind == "internet"), None)
    findings = []
    for node_id in sorted(graph):
        if node_id == internet:
            continue
        if internet is not None:
            kept = _reach(graph, internet, removed=node_id)
            stranded = sorted(_reach(graph, internet) - kept - {node_id})
            to = _name(project, internet)
        else:
            groups = sorted(_components(graph, node_id), key=lambda g: (-len(g), sorted(g)))
            stranded = sorted(set().union(*groups[1:])) if len(groups) > 1 else []
            to = "the rest of the network"
        if stranded:
            names = ", ".join(_name(project, n) for n in stranded)
            verb = "loses" if len(stranded) == 1 else "lose"
            findings.append(
                Finding(
                    Check.SINGLE_POINT_OF_FAILURE,
                    Severity.INFO,
                    f"If {_name(project, node_id)} fails, {names} {verb} the connection to {to}",
                    (node_id, *stranded),
                )
            )
    return findings
