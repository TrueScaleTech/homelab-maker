"""Structural checks: rules that span several values of a project.

A value that is wrong on its own (a VLAN of 5000) cannot be built at all; see
``model``. What is left here is consistency between values: a cable to a node that does
not exist, a container inside a switch, a ninth cable on an eight-port switch. A project
that fails these checks is refused when loaded, because the analysis relies on them.

Whether a homelab is *well designed* (duplicate addresses, VLAN mismatches, single points
of failure) is a different question, answered by checks that report warnings instead.
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from homelab_maker.catalog import CATALOG
from homelab_maker.model import (
    ANY,
    PHYSICAL_MEDIA,
    Link,
    Node,
    Project,
    is_network,
    node_routes,
)


class Code(StrEnum):
    DUPLICATE_ID = "duplicate-id"
    UNKNOWN_KIND = "unknown-kind"
    UNKNOWN_PARENT = "unknown-parent"
    PARENT_CYCLE = "parent-cycle"
    BAD_NESTING = "bad-nesting"
    DUPLICATE_INTERFACE = "duplicate-interface"
    LINK_ENDPOINT = "link-endpoint"
    LINK_TO_SELF = "link-to-self"
    PORT_BUSY = "port-busy"
    CELL_TAKEN = "cell-taken"
    RULE_ON_NON_ROUTER = "rule-on-non-router"
    RULE_REFERENCE = "rule-reference"
    FLOW_ENDPOINT = "flow-endpoint"
    FLOW_TO_SELF = "flow-to-self"


@dataclass(frozen=True, slots=True)
class Problem:
    code: Code
    # The id of the thing that is wrong, so the editor can select it.
    subject: str
    message: str


def validate(project: Project) -> list[Problem]:
    """Every structural problem of ``project``, in a stable order. Empty means consistent."""
    problems: list[Problem] = []
    by_id = {node.id: node for node in project.nodes}

    _duplicate_ids(project, problems)
    for node in project.nodes:
        _check_node(node, by_id, problems)
    _check_cells(project, problems)
    _check_links(project, by_id, problems)
    _check_flows(project, by_id, problems)

    return sorted(problems, key=lambda p: (p.subject, p.code.value, p.message))


def _duplicate_ids(project: Project, problems: list[Problem]) -> None:
    groups = (
        ("node", [n.id for n in project.nodes]),
        ("link", [link.id for link in project.links]),
        ("zone", [z.id for z in project.zones]),
        ("flow", [f.id for f in project.flows]),
    )
    for what, ids in groups:
        counts: dict[str, int] = defaultdict(int)
        for ident in ids:
            counts[ident] += 1
        for ident, count in counts.items():
            if count > 1:
                problems.append(
                    Problem(
                        Code.DUPLICATE_ID, ident, f"the {what} id {ident!r} is used {count} times"
                    )
                )


def _check_node(node: Node, by_id: dict[str, Node], problems: list[Problem]) -> None:
    kind = CATALOG.get(node.kind)
    if kind is None:
        problems.append(
            Problem(
                Code.UNKNOWN_KIND, node.id, f"{node.id!r} has the unknown device kind {node.kind!r}"
            )
        )

    seen: set[str] = set()
    for interface in node.interfaces:
        if interface.name in seen:
            problems.append(
                Problem(
                    Code.DUPLICATE_INTERFACE,
                    node.id,
                    f"{node.id!r} has two interfaces named {interface.name!r}",
                )
            )
        seen.add(interface.name)

    if node.parent is not None:
        parent = by_id.get(node.parent)
        if parent is None:
            problems.append(
                Problem(
                    Code.UNKNOWN_PARENT,
                    node.id,
                    f"{node.id!r} sits inside the missing {node.parent!r}",
                )
            )
        else:
            parent_kind = CATALOG.get(parent.kind)
            if kind and parent_kind and kind.key not in parent_kind.contains:
                problems.append(
                    Problem(
                        Code.BAD_NESTING,
                        node.id,
                        f"a {kind.label.lower()} cannot sit inside a {parent_kind.label.lower()}",
                    )
                )
        if _is_in_cycle(node.id, by_id):
            problems.append(
                Problem(
                    Code.PARENT_CYCLE,
                    node.id,
                    f"{node.id!r} is, through its parents, inside itself",
                )
            )

    if node.rules and not node_routes(node):
        problems.append(
            Problem(
                Code.RULE_ON_NON_ROUTER,
                node.id,
                f"{node.id!r} has rules but does not forward traffic, so they would never apply",
            )
        )
    for rule in node.rules:
        for reference in (rule.source, rule.destination):
            if reference != ANY and not is_network(reference) and reference not in by_id:
                problems.append(
                    Problem(
                        Code.RULE_REFERENCE,
                        node.id,
                        f"a rule of {node.id!r} names the missing node {reference!r}",
                    )
                )


def _is_in_cycle(node_id: str, by_id: dict[str, Node]) -> bool:
    """Whether following parents from ``node_id`` leads back to ``node_id``."""
    seen: set[str] = set()
    current = by_id.get(node_id)
    while current is not None and current.parent is not None:
        if current.parent == node_id:
            return True
        if current.parent in seen:
            # Entered a loop that does not include this node (it hangs off one).
            return False
        seen.add(current.parent)
        current = by_id.get(current.parent)
    return False


def _check_cells(project: Project, problems: list[Problem]) -> None:
    cells: dict[tuple[str | None, int, int], str] = {}
    for node in project.nodes:
        cell = (node.parent, node.x, node.y)
        first = cells.setdefault(cell, node.id)
        if first != node.id:
            problems.append(
                Problem(
                    Code.CELL_TAKEN,
                    node.id,
                    f"{node.id!r} is on the same grid cell ({node.x}, {node.y}) as {first!r}",
                )
            )


def _check_links(project: Project, by_id: dict[str, Node], problems: list[Problem]) -> None:
    usage: dict[tuple[str, str], list[Link]] = defaultdict(list)
    for link in project.links:
        for end in (link.a, link.b):
            node = by_id.get(end.node)
            if node is None:
                problems.append(
                    Problem(
                        Code.LINK_ENDPOINT,
                        link.id,
                        f"link {link.id!r} ends on the missing node {end.node!r}",
                    )
                )
            elif all(interface.name != end.interface for interface in node.interfaces):
                problems.append(
                    Problem(
                        Code.LINK_ENDPOINT,
                        link.id,
                        f"link {link.id!r} ends on {end.node!r}, which has no {end.interface!r}",
                    )
                )
            else:
                usage[(end.node, end.interface)].append(link)
        if link.a.node == link.b.node:
            problems.append(
                Problem(
                    Code.LINK_TO_SELF, link.id, f"link {link.id!r} joins {link.a.node!r} to itself"
                )
            )

    for (node_id, interface), links in sorted(usage.items()):
        if len(links) > 1 and any(link.medium in PHYSICAL_MEDIA for link in links):
            problems.append(
                Problem(
                    Code.PORT_BUSY,
                    f"{node_id}:{interface}",
                    f"{interface!r} of {node_id!r} has {len(links)} links; a cable fills a port",
                )
            )


def _check_flows(project: Project, by_id: dict[str, Node], problems: list[Problem]) -> None:
    for flow in project.flows:
        for role, node_id in (("source", flow.source), ("destination", flow.destination)):
            if node_id not in by_id:
                problems.append(
                    Problem(
                        Code.FLOW_ENDPOINT,
                        flow.id,
                        f"flow {flow.id!r} has the missing {role} {node_id!r}",
                    )
                )
        if flow.source == flow.destination:
            problems.append(
                Problem(
                    Code.FLOW_TO_SELF,
                    flow.id,
                    f"flow {flow.id!r} goes from {flow.source!r} to itself",
                )
            )
