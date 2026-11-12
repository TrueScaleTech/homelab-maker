"""What goes down if this is switched off?

Remove some devices (and everything inside them) from the drawing, run the same analysis,
and compare: which flows worked before and do not now, and which devices that still run
have lost their way to the Internet. Nothing is changed in the project itself.
"""

from collections.abc import Collection
from dataclasses import dataclass, replace

from homelab_maker.checks import adjacency, reach
from homelab_maker.model import Project
from homelab_maker.reachability import Reason, Result, Verdict, analyse_all


@dataclass(frozen=True, slots=True)
class Outage:
    # Everything that stops: the devices chosen and what was inside them.
    stopped: tuple[str, ...]
    # Flows that worked before and do not now, with the reason they fail.
    broken: tuple[Result, ...]
    # Devices that still run but cannot reach the Internet (or the rest of the network).
    cut_off: tuple[str, ...]

    @property
    def harmless(self) -> bool:
        return not self.broken and not self.cut_off


def with_descendants(project: Project, node_ids: Collection[str]) -> set[str]:
    stopped = set(node_ids)
    grew = True
    while grew:
        grew = False
        for node in project.nodes:
            if node.parent in stopped and node.id not in stopped:
                stopped.add(node.id)
                grew = True
    return stopped


def without(project: Project, node_ids: Collection[str]) -> Project:
    """The project as it would be with these devices (and what is inside them) switched off."""
    stopped = with_descendants(project, node_ids)
    return replace(
        project,
        nodes=tuple(n for n in project.nodes if n.id not in stopped),
        links=tuple(
            link
            for link in project.links
            if link.a.node not in stopped and link.b.node not in stopped
        ),
    )


def what_goes_down(project: Project, switched_off: Collection[str]) -> Outage:
    stopped = with_descendants(project, switched_off)
    before = analyse_all(project)
    reduced = without(project, switched_off)
    after = {r.flow: r for r in analyse_all(reduced)} if reduced.flows else {}

    broken: list[Result] = []
    flows = {flow.id: flow for flow in project.flows}
    for result in before:
        if not result.reachable:
            continue
        flow = flows[result.flow]
        gone = next((n for n in (flow.source, flow.destination) if n in stopped), None)
        if gone is not None:
            name = project.node(gone)
            broken.append(
                Result(
                    result.flow,
                    Verdict.BLOCKED,
                    Reason.MISSING,
                    f"{name.name if name else gone} is switched off",
                    result.path,
                    result.links,
                    gone,
                    (),
                )
            )
        elif not after[result.flow].reachable:
            broken.append(after[result.flow])

    return Outage(tuple(sorted(stopped)), tuple(broken), _cut_off(project, stopped))


def _cut_off(project: Project, stopped: set[str]) -> tuple[str, ...]:
    graph = adjacency(project)
    if not graph:
        return ()
    removed_cards = {card for card in graph if card in stopped}
    internet = next(
        (n.id for n in project.children(None) if n.kind == "internet" and n.id not in stopped),
        None,
    )
    if internet is None:
        # No Internet to measure against: the biggest group that is left is the "rest".
        survivors = [n for n in graph if n not in removed_cards]
        if not survivors:
            return ()
        internet = max(survivors, key=lambda n: (len(reach(graph, n)), n))
    before = reach(graph, internet)
    after = reach(graph, internet, removed=removed_cards)
    return tuple(sorted(before - after - removed_cards))


def describe(project: Project, outage: Outage) -> str:
    """The outage in a few lines of plain text, for a message box."""

    def names(ids: Collection[str]) -> str:
        found = (project.node(i) for i in sorted(ids))
        return ", ".join(node.name for node in found if node is not None)

    lines = [f"Switched off: {names(outage.stopped)}."]
    if outage.harmless:
        lines.append("Nothing else is affected, as far as the drawing shows.")
        return "\n".join(lines)
    if outage.cut_off:
        lines.append(f"Still running but cut off: {names(outage.cut_off)}.")
    if outage.broken:
        lines.append("Flows that stop working:")
        flows = {flow.id: flow for flow in project.flows}
        for result in outage.broken:
            flow = flows[result.flow]
            what = flow.description or f"{flow.protocol.value}/{flow.port}"
            ends = f"{names([flow.source])} to {names([flow.destination])}"
            lines.append(f"  - {ends} ({what}): {result.detail}")
    return "\n".join(lines)
