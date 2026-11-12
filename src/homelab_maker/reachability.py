"""Reachability: can one device reach a service of another, along which path, and what stops it?

The answer is about the drawing, not about the real network. It follows the links that were
drawn; it lets traffic cross a link only when both ports carry the same VLAN; it lets a
VLAN change only at a device that routes; it applies the rules of every device that routes
on the way, first match wins, and allows what no rule mentions; and it checks that the
destination lists a service on the port. ``NOT_MODELLED`` says what it leaves out, and the
window shows that text next to every answer.

A virtual machine or container is attached to its host without a cable: traffic from a
guest leaves through the host's ports, and traffic for a guest arrives through them. A
guest with no VLAN of its own follows its host.

This module knows nothing about the window.
"""

import ipaddress
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from homelab_maker.catalog import CATALOG
from homelab_maker.model import (
    ANY,
    Flow,
    Interface,
    InterfaceMode,
    Link,
    Medium,
    Node,
    Project,
    Rule,
    RuleAction,
    is_network,
    node_routes,
)

# "Not tied to a VLAN": a tunnel, or a guest that follows its host.
NO_VLAN = 0
DEFAULT_VLAN = 1

# Searching stops after this many partial paths, which is far more than a homelab needs.
MAX_SEARCH = 20_000
MAX_LENGTH = 40

NOT_MODELLED = (
    "NAT and port forwarding",
    "dynamic routing and routing tables (a router is assumed to reach every network it touches)",
    "ARP, DHCP and DNS",
    "return traffic (a reply is assumed to be allowed)",
    "bandwidth, latency and wireless roaming",
    "the state of a real firewall",
)


class Verdict(StrEnum):
    REACHABLE = "reachable"
    BLOCKED = "blocked"


class Reason(StrEnum):
    NO_PATH = "no-path"
    VLAN = "vlan"
    RULE = "rule"
    NO_SERVICE = "no-service"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class Result:
    flow: str
    verdict: Verdict
    reason: Reason | None
    # One sentence: how it gets there, or the first thing that stops it.
    detail: str
    # The devices along the path, source first. For a blocked flow, the path that was
    # tried (empty when no cable path exists).
    path: tuple[str, ...]
    # The links used between consecutive devices; "" where a guest meets its host.
    links: tuple[str, ...]
    # The device or link that stops it, when something does.
    stopped_at: str | None
    notes: tuple[str, ...]

    @property
    def reachable(self) -> bool:
        return self.verdict is Verdict.REACHABLE


# ------------------------------------------------------------------------------ VLANs


def vlans_of(interface: Interface) -> frozenset[int]:
    """The VLANs a port carries: its untagged one, plus the tagged ones of a trunk."""
    native = interface.vlan or DEFAULT_VLAN
    if interface.mode is InterfaceMode.TRUNK:
        return frozenset({native, *interface.trunk_vlans})
    return frozenset({native})


def accepts(interface: Interface, vlan: int) -> bool:
    return vlan == NO_VLAN or vlan in vlans_of(interface)


def describe_vlans(interface: Interface) -> str:
    native = interface.vlan or DEFAULT_VLAN
    if interface.mode is InterfaceMode.TRUNK and interface.trunk_vlans:
        tagged = ", ".join(str(v) for v in interface.trunk_vlans)
        return f"VLAN {native} untagged and {tagged} tagged"
    return f"VLAN {native}"


def describe_rule(rule: Rule) -> str:
    what = rule.protocol.value + (f"/{rule.port}" if rule.port is not None else "")
    return f"{rule.action.value} {what} from {rule.source} to {rule.destination}"


# ------------------------------------------------------------------------------- search


@dataclass(frozen=True, slots=True)
class _Step:
    node: str
    vlan: int
    # The link used to get here; "" where a guest meets its host; None at the start.
    link: str | None
    out_port: str | None
    in_port: str | None


class _Net:
    """The project indexed for searching."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.nodes = {node.id: node for node in project.nodes}
        self.links = {link.id: link for link in project.links}
        self.attached: dict[str, list[tuple[Link, str, str, str]]] = {n: [] for n in self.nodes}
        for link in project.links:
            for mine, theirs in ((link.a, link.b), (link.b, link.a)):
                if mine.node in self.attached and theirs.node in self.nodes:
                    self.attached[mine.node].append(
                        (link, mine.interface, theirs.node, theirs.interface)
                    )

    def interface(self, node_id: str, name: str | None) -> Interface | None:
        node = self.nodes.get(node_id)
        return next((i for i in node.interfaces if i.name == name), None) if node else None

    def forwards(self, node: Node) -> bool:
        kind = CATALOG.get(node.kind)
        return node_routes(node) or bool(kind and kind.carries)

    def ancestors(self, node_id: str) -> list[str]:
        found: list[str] = []
        node = self.nodes.get(node_id)
        while node is not None and node.parent in self.nodes and node.parent not in found:
            found.append(node.parent)
            node = self.nodes[node.parent]
        return found

    def child_toward(self, host: str, target: str) -> str | None:
        """The guest of ``host`` that is, or holds, ``target``."""
        chain = [target, *self.ancestors(target)]
        if host not in chain:
            return None
        index = chain.index(host)
        return chain[index - 1] if index > 0 else None

    def guest_vlan(self, node: Node) -> int:
        return next((i.vlan for i in node.interfaces if i.vlan is not None), NO_VLAN)

    def guest_accepts(self, node: Node, vlan: int) -> bool:
        if vlan == NO_VLAN or all(i.vlan is None for i in node.interfaces):
            return True
        return any(accepts(i, vlan) for i in node.interfaces)


def _moves(
    net: _Net, steps: tuple[_Step, ...], up: bool, target: str, strict: bool
) -> Iterator[tuple[_Step, bool]]:
    here = steps[-1]
    node = net.nodes[here.node]

    # Down into a guest on the way to the target.
    child = net.child_toward(node.id, target)
    if child is not None and (not strict or net.guest_accepts(net.nodes[child], here.vlan)):
        yield _Step(child, here.vlan, "", None, None), False

    # Up to the host that carries a guest's traffic.
    if up and node.parent in net.nodes:
        vlan = net.guest_vlan(node) if strict else NO_VLAN
        yield _Step(str(node.parent), vlan, "", None, None), True

    if not (up or net.forwards(node)):
        return
    for link, port, other, other_port in net.attached[node.id]:
        if link.id == here.link:
            continue
        port_interface = net.interface(node.id, port)
        arrive = net.interface(other, other_port)
        if port_interface is None or arrive is None:
            continue
        if not strict or link.medium is Medium.VPN:
            leaving = {NO_VLAN}
        elif (up and here.vlan == NO_VLAN) or node_routes(node) or here.vlan == NO_VLAN:
            leaving = set(vlans_of(port_interface))
        else:
            leaving = {here.vlan} if accepts(port_interface, here.vlan) else set()
        for vlan in sorted(leaving):
            if strict and link.medium is not Medium.VPN and not accepts(arrive, vlan):
                continue
            yield _Step(other, vlan, link.id, port, other_port), False


def _paths(net: _Net, source: str, target: str, *, strict: bool) -> Iterator[tuple[_Step, ...]]:
    """Every way from ``source`` to ``target``, shortest first."""
    queue: deque[tuple[tuple[_Step, ...], bool]] = deque(
        [((_Step(source, NO_VLAN, None, None, None),), True)]
    )
    pops = 0
    while queue and pops < MAX_SEARCH:
        steps, up = queue.popleft()
        pops += 1
        if steps[-1].node == target and len(steps) > 1:
            yield steps
            continue
        if len(steps) >= MAX_LENGTH:
            continue
        seen = {(s.node, s.vlan) for s in steps}
        for step, still_up in _moves(net, steps, up, target, strict):
            if (step.node, step.vlan) not in seen:
                queue.append(((*steps, step), still_up))


# --------------------------------------------------------------------------------- rules


def _matches(spec: str, net: _Net, node_id: str) -> bool:
    if spec == ANY:
        return True
    if is_network(spec):
        network = ipaddress.ip_network(spec, strict=False)
        node = net.nodes[node_id]
        for interface in node.interfaces:
            for address in interface.addresses:
                host = ipaddress.ip_interface(address).ip
                if host.version == network.version and host in network:
                    return True
        return False
    return spec == node_id or spec in net.ancestors(node_id)


def _first_denial(net: _Net, steps: tuple[_Step, ...], flow: Flow) -> tuple[Node, int, Rule] | None:
    """The first rule on the path that denies the flow, if a deny is what decides it."""
    for step in steps[1:-1]:
        node = net.nodes[step.node]
        if not node_routes(node):
            continue
        for number, rule in enumerate(node.rules, start=1):
            if not (
                _matches(rule.source, net, flow.source)
                and _matches(rule.destination, net, flow.destination)
            ):
                continue
            if rule.protocol.value not in (ANY, flow.protocol.value):
                continue
            if rule.port is not None and rule.port != flow.port:
                continue
            if rule.action is RuleAction.DENY:
                return node, number, rule
            break  # an allow decides it, so the rules below are never looked at
    return None


# ------------------------------------------------------------------------------ diagnosis


def _diagnose(net: _Net, steps: tuple[_Step, ...]) -> tuple[str, str | None]:
    """Why a path made only of cables cannot carry traffic: the first VLAN that gets stuck."""
    possible: set[int] = {NO_VLAN}
    as_source = True
    for before, after in pairwise(steps):
        node_before = net.nodes[before.node]
        if after.link == "":
            as_source = after.node in net.ancestors(before.node)
            if as_source:
                possible = {NO_VLAN}
            continue
        link = net.links.get(str(after.link))
        out = net.interface(before.node, after.out_port)
        into = net.interface(after.node, after.in_port)
        if link is None or out is None or into is None:
            continue
        if link.medium is Medium.VPN:
            possible, as_source = {NO_VLAN}, False
            continue
        carried = set(vlans_of(out))
        allowed = (
            carried
            if (NO_VLAN in possible or as_source or node_routes(node_before))
            else possible & carried
        )
        if not allowed:
            wanted = ", ".join(str(v) for v in sorted(possible))
            return (
                f"VLAN {wanted} cannot leave {node_before.name} through {out.name}, "
                f"which carries {describe_vlans(out)}",
                before.node,
            )
        crossing = {v for v in allowed if accepts(into, v)}
        if not crossing:
            node_after = net.nodes[after.node]
            return (
                f"{node_before.name} ({out.name}, {describe_vlans(out)}) is joined to "
                f"{node_after.name} ({into.name}, {describe_vlans(into)}), but they share no VLAN",
                str(after.link),
            )
        possible, as_source = crossing, False
    return "the VLANs along the path do not line up", None


# ----------------------------------------------------------------------------- the answer


def _name(net: _Net, node_id: str) -> str:
    node = net.nodes.get(node_id)
    return node.name if node else node_id


def _route_text(net: _Net, steps: tuple[_Step, ...]) -> str:
    names = [_name(net, s.node) for s in steps]
    return " → ".join(names)


def _analyse(net: _Net, flow: Flow) -> Result:
    for role, node_id in (("source", flow.source), ("destination", flow.destination)):
        if node_id not in net.nodes:
            return Result(
                flow.id,
                Verdict.BLOCKED,
                Reason.MISSING,
                f"the {role} {node_id!r} does not exist",
                (),
                (),
                None,
                (),
            )
    source, target = net.nodes[flow.source], net.nodes[flow.destination]

    delivered = list(_paths(net, flow.source, flow.destination, strict=True))
    if not delivered:
        plain = next(_paths(net, flow.source, flow.destination, strict=False), None)
        if plain is None:
            return Result(
                flow.id,
                Verdict.BLOCKED,
                Reason.NO_PATH,
                f"no chain of cables or links joins {source.name} to {target.name}",
                (),
                (),
                None,
                (),
            )
        detail, stopped = _diagnose(net, plain)
        return Result(
            flow.id,
            Verdict.BLOCKED,
            Reason.VLAN,
            detail,
            tuple(s.node for s in plain),
            _links(plain),
            stopped,
            (),
        )

    denied: tuple[tuple[Node, int, Rule], tuple[_Step, ...]] | None = None
    chosen: tuple[_Step, ...] | None = None
    for steps in delivered:
        denial = _first_denial(net, steps, flow)
        if denial is None:
            chosen = steps
            break
        if denied is None:
            denied = (denial, steps)
    if chosen is None:
        if denied is None:  # unreachable: delivered is not empty and none was chosen
            raise RuntimeError("a delivered path was neither allowed nor denied")
        (node, number, rule), steps = denied
        return Result(
            flow.id,
            Verdict.BLOCKED,
            Reason.RULE,
            f"{node.name} denies it with rule {number} ({describe_rule(rule)})",
            tuple(s.node for s in steps),
            _links(steps),
            node.id,
            (),
        )

    notes: list[str] = []
    if target.services:
        listens = any(s.port == flow.port and s.protocol == flow.protocol for s in target.services)
        if not listens:
            return Result(
                flow.id,
                Verdict.BLOCKED,
                Reason.NO_SERVICE,
                f"{target.name} has no service on {flow.protocol.value}/{flow.port}",
                tuple(s.node for s in chosen),
                _links(chosen),
                target.id,
                (),
            )
    else:
        notes.append(f"{target.name} lists no services, so the port was not checked")
    return Result(
        flow.id,
        Verdict.REACHABLE,
        None,
        f"via {_route_text(net, chosen)}",
        tuple(s.node for s in chosen),
        _links(chosen),
        None,
        tuple(notes),
    )


def _links(steps: tuple[_Step, ...]) -> tuple[str, ...]:
    return tuple(s.link or "" for s in steps[1:])


def analyse_flow(project: Project, flow: Flow) -> Result:
    return _analyse(_Net(project), flow)


def analyse_all(project: Project) -> tuple[Result, ...]:
    """The answer for every flow of the project, in the order of the flows."""
    net = _Net(project)
    return tuple(_analyse(net, flow) for flow in project.flows)
