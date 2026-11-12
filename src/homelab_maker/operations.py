"""Editing operations: each takes a project and returns a new, consistent one.

They are pure functions, so every edit the window offers is tested without a window, and
undo is simply "go back to the previous project". An operation that cannot be done
raises ``ValueError`` and leaves the project as it was.
"""

from collections.abc import Collection
from dataclasses import replace

from homelab_maker.catalog import CATALOG
from homelab_maker.model import (
    GRID_LIMIT,
    Node,
    Project,
    new_node,
)

# How far from the wanted cell a free one is looked for before giving up.
_SEARCH_RADIUS = 60


def _siblings_cells(
    project: Project, parent: str | None, ignore: Collection[str] = ()
) -> set[tuple[int, int]]:
    return {
        (node.x, node.y)
        for node in project.nodes
        if node.parent == parent and node.id not in ignore
    }


def nearest_free_cell(
    project: Project, x: int, y: int, parent: str | None = None
) -> tuple[int, int]:
    """The free cell closest to ``(x, y)`` among the nodes that share a parent."""
    taken = _siblings_cells(project, parent)
    for radius in range(_SEARCH_RADIUS + 1):
        ring = [
            (x + dx, y + dy)
            for dx in range(-radius, radius + 1)
            for dy in range(-radius, radius + 1)
            if max(abs(dx), abs(dy)) == radius
        ]
        # Closest first, then top-to-bottom and left-to-right, so the result is predictable.
        ring.sort(key=lambda cell: ((cell[0] - x) ** 2 + (cell[1] - y) ** 2, cell[1], cell[0]))
        for cx, cy in ring:
            if abs(cx) <= GRID_LIMIT and abs(cy) <= GRID_LIMIT and (cx, cy) not in taken:
                return cx, cy
    raise ValueError("there is no free cell near that spot")


def display_name(project: Project, base: str) -> str:
    """``base`` if no node has that name, otherwise ``base 2``, ``base 3``, and so on."""
    used = {node.name for node in project.nodes}
    candidate = base
    number = 2
    while candidate in used:
        candidate = f"{base} {number}"
        number += 1
    return candidate


def add_node(project: Project, kind_key: str, x: int, y: int) -> tuple[Project, str]:
    """Place a new device of a catalogue kind on the free cell nearest to ``(x, y)``.

    Returns the new project and the id of the node that was added.
    """
    kind = CATALOG.get(kind_key)
    if kind is None:
        raise ValueError(f"unknown device kind {kind_key!r}")
    cell_x, cell_y = nearest_free_cell(project, x, y)
    node = new_node(
        kind_key,
        display_name(project, kind.label),
        [existing.id for existing in project.nodes],
        x=cell_x,
        y=cell_y,
    )
    return replace(project, nodes=(*project.nodes, node)), node.id


def can_move(project: Project, node_ids: Collection[str], dx: int, dy: int) -> bool:
    """Whether moving these nodes by ``(dx, dy)`` cells keeps every one on its own cell."""
    moving = [node for node in project.nodes if node.id in node_ids]
    if not moving:
        return False
    for node in moving:
        if abs(node.x + dx) > GRID_LIMIT or abs(node.y + dy) > GRID_LIMIT:
            return False
    for parent in {node.parent for node in moving}:
        taken = _siblings_cells(project, parent, ignore=node_ids)
        for node in moving:
            if node.parent == parent and (node.x + dx, node.y + dy) in taken:
                return False
    return True


def move_nodes(project: Project, node_ids: Collection[str], dx: int, dy: int) -> Project:
    """Move nodes by whole cells. Nodes inside a moved host keep their place inside it."""
    if not can_move(project, node_ids, dx, dy):
        raise ValueError("that move would put a device on a cell that is taken")
    nodes = tuple(
        replace(node, x=node.x + dx, y=node.y + dy) if node.id in node_ids else node
        for node in project.nodes
    )
    return replace(project, nodes=nodes)


def rename_node(project: Project, node_id: str, name: str) -> Project:
    if project.node(node_id) is None:
        raise ValueError(f"there is no node {node_id!r}")
    nodes = tuple(
        replace(node, name=name.strip()) if node.id == node_id else node for node in project.nodes
    )
    return replace(project, nodes=nodes)


def _with_descendants(project: Project, node_ids: Collection[str]) -> set[str]:
    doomed = set(node_ids)
    grew = True
    while grew:
        grew = False
        for node in project.nodes:
            if node.parent in doomed and node.id not in doomed:
                doomed.add(node.id)
                grew = True
    return doomed


def delete_nodes(project: Project, node_ids: Collection[str]) -> Project:
    """Remove nodes, everything inside them, and everything that pointed at them.

    Cables to a removed node go, flows from or to it go, and rules that named it are
    dropped, so the result is always consistent.
    """
    doomed = _with_descendants(project, node_ids)
    kept: list[Node] = []
    for node in project.nodes:
        if node.id in doomed:
            continue
        rules = tuple(
            rule
            for rule in node.rules
            if rule.source not in doomed and rule.destination not in doomed
        )
        kept.append(node if rules == node.rules else replace(node, rules=rules))
    return replace(
        project,
        nodes=tuple(kept),
        links=tuple(
            link
            for link in project.links
            if link.a.node not in doomed and link.b.node not in doomed
        ),
        flows=tuple(
            flow
            for flow in project.flows
            if flow.source not in doomed and flow.destination not in doomed
        ),
    )
