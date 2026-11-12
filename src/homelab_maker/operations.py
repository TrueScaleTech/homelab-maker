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
    PHYSICAL_MEDIA,
    Endpoint,
    Interface,
    Link,
    Medium,
    Node,
    Project,
    new_node,
    slugify,
    unique_id,
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


def check_can_contain(project: Project, parent_id: str | None, kind_key: str) -> None:
    """Raise ``ValueError`` unless a node of ``kind_key`` may sit inside ``parent_id``."""
    if parent_id is None:
        return
    parent = project.node(parent_id)
    if parent is None:
        raise ValueError(f"there is no node {parent_id!r}")
    parent_kind, kind = CATALOG.get(parent.kind), CATALOG.get(kind_key)
    if parent_kind is None or kind is None or kind_key not in parent_kind.contains:
        what = kind.label.lower() if kind else kind_key
        host = parent_kind.label.lower() if parent_kind else parent.kind
        raise ValueError(f"a {what} cannot sit inside a {host}")


def can_contain(project: Project, parent_id: str | None, kind_key: str) -> bool:
    try:
        check_can_contain(project, parent_id, kind_key)
    except ValueError:
        return False
    return True


def add_node(
    project: Project, kind_key: str, x: int, y: int, parent: str | None = None
) -> tuple[Project, str]:
    """Place a new device of a catalogue kind on the free cell nearest to ``(x, y)``.

    With ``parent`` the device is placed inside that host, on one of its own cells.
    Returns the new project and the id of the node that was added.
    """
    kind = CATALOG.get(kind_key)
    if kind is None:
        raise ValueError(f"unknown device kind {kind_key!r}")
    check_can_contain(project, parent, kind_key)
    cell_x, cell_y = nearest_free_cell(project, x, y, parent)
    node = new_node(
        kind_key,
        display_name(project, kind.label),
        [existing.id for existing in project.nodes],
        x=cell_x,
        y=cell_y,
        parent=parent,
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


# ------------------------------------------------------------------------------ nesting


def replace_node(project: Project, node: Node) -> Project:
    """The project with the node of the same id swapped for ``node``."""
    nodes = tuple(node if item.id == node.id else item for item in project.nodes)
    return replace(project, nodes=nodes)


def move_into(project: Project, node_ids: Collection[str], parent: str | None) -> Project:
    """Put nodes inside a host (or back on the canvas for ``None``), keeping what they hold.

    Each node takes the free cell nearest to the one it had. Cables stay as they are.
    """
    moving = [node for node in project.nodes if node.id in node_ids]
    if not moving:
        raise ValueError("there is nothing to move")
    if parent is not None and parent in _with_descendants(project, node_ids):
        raise ValueError("a device cannot be put inside itself")
    for node in moving:
        check_can_contain(project, parent, node.kind)
    result = project
    for node in moving:
        if node.parent == parent:
            continue
        x, y = nearest_free_cell(result, node.x, node.y, parent)
        result = replace_node(result, replace(node, parent=parent, x=x, y=y))
    return result


def move_out(project: Project, node_ids: Collection[str]) -> Project:
    """Take nodes out of their host, one level up, beside the host they came out of."""
    result = project
    for node in [n for n in project.nodes if n.id in node_ids and n.parent is not None]:
        host = project.node(node.parent) if node.parent else None
        if host is None:
            continue
        spot = replace(node, x=host.x, y=host.y)
        result = move_into(replace_node(result, spot), [node.id], host.parent)
    return result


# ------------------------------------------------------------------------------ cables


def interface_links(project: Project, node_id: str, interface: str) -> tuple[Link, ...]:
    """The links that end on one interface."""
    end = Endpoint(node_id, interface)
    return tuple(link for link in project.links if end in (link.a, link.b))


def _used(project: Project) -> set[tuple[str, str]]:
    """The interfaces that have any link at all."""
    return {(end.node, end.interface) for link in project.links for end in (link.a, link.b)}


def _cabled(project: Project) -> set[tuple[str, str]]:
    """The interfaces that have a cable (ethernet or fibre) plugged in."""
    return {
        (end.node, end.interface)
        for link in project.links
        if link.medium in PHYSICAL_MEDIA
        for end in (link.a, link.b)
    }


# Wireless and tunnel links get an interface of their own, so a cable can never end up
# sharing a port with a radio.
_RADIO_PREFIX = {Medium.WIFI: "wlan", Medium.VPN: "tun"}


def free_interface(project: Project, node_id: str, medium: Medium) -> str | None:
    """The interface of a node that the next link of this medium would use.

    A cable (ethernet or fibre) needs a port nothing is plugged into. A wireless or tunnel
    link uses the node's ``wlan`` or ``tun`` interface, which many links may share; ``None``
    means there is none yet (``connect`` adds one).
    """
    node = project.node(node_id)
    if node is None:
        return None
    if medium in PHYSICAL_MEDIA:
        used = _used(project)
        return next((i.name for i in node.interfaces if (node_id, i.name) not in used), None)
    cabled = _cabled(project)
    prefix = _RADIO_PREFIX[medium]
    return next(
        (
            i.name
            for i in node.interfaces
            if i.name.startswith(prefix) and (node_id, i.name) not in cabled
        ),
        None,
    )


def _ancestors(project: Project, node_id: str) -> set[str]:
    found: set[str] = set()
    node = project.node(node_id)
    while node is not None and node.parent is not None and node.parent not in found:
        found.add(node.parent)
        node = project.node(node.parent)
    return found


def connect(
    project: Project,
    first: str,
    second: str,
    medium: Medium = Medium.ETHERNET,
    first_interface: str | None = None,
    second_interface: str | None = None,
) -> tuple[Project, str]:
    """Join two devices with a link. Returns the new project and the id of the link.

    Without an interface name the first free one is used; a wireless or tunnel link adds
    a ``wlan`` or ``tun`` interface to a device that has none. A cable never goes on a
    port that already has a link.
    """
    if first == second:
        raise ValueError("a device cannot be cabled to itself")
    result = project
    ends: list[Endpoint] = []
    for node_id, wanted in ((first, first_interface), (second, second_interface)):
        node = result.node(node_id)
        if node is None:
            raise ValueError(f"there is no node {node_id!r}")
        name = wanted if wanted is not None else free_interface(result, node_id, medium)
        if name is None and medium not in PHYSICAL_MEDIA:
            prefix = _RADIO_PREFIX[medium]
            taken = {i.name for i in node.interfaces}
            number = 0
            while f"{prefix}{number}" in taken:
                number += 1
            result, name = add_interface(result, node_id, f"{prefix}{number}")
        if name is None:
            raise ValueError(f"{node.name} has no free port")
        if all(i.name != name for i in node.interfaces) and not (
            medium not in PHYSICAL_MEDIA and wanted is None
        ):
            raise ValueError(f"{node.name} has no port {name!r}")
        if (node_id, name) in _cabled(result) or (
            medium in PHYSICAL_MEDIA and (node_id, name) in _used(result)
        ):
            what = "a cable" if (node_id, name) in _cabled(result) else "a link"
            raise ValueError(f"{name} of {node.name} already has {what}")
        ends.append(Endpoint(node_id, name))
    if first in _ancestors(result, second) or second in _ancestors(result, first):
        raise ValueError("a device inside a host is already attached to it")
    link_id = unique_id([link.id for link in result.links], slugify(f"{first}-{second}"))
    link = Link(link_id, ends[0], ends[1], medium)
    return replace(result, links=(*result.links, link)), link_id


def disconnect(project: Project, link_ids: Collection[str]) -> Project:
    """Remove links."""
    known = {link.id for link in project.links}
    missing = sorted(set(link_ids) - known)
    if missing:
        raise ValueError(f"there is no link {missing[0]!r}")
    return replace(project, links=tuple(link for link in project.links if link.id not in link_ids))


def add_interface(project: Project, node_id: str, name: str | None = None) -> tuple[Project, str]:
    """Give a node one more interface, named after its kind unless a name is given."""
    node = project.node(node_id)
    if node is None:
        raise ValueError(f"there is no node {node_id!r}")
    taken = {i.name for i in node.interfaces}
    if name is None:
        kind = CATALOG.get(node.kind)
        prefix = kind.port_prefix if kind else "eth"
        number = 1
        while f"{prefix}{number}" in taken:
            number += 1
        name = f"{prefix}{number}"
    name = name.strip()
    if name in taken:
        raise ValueError(f"{node.name} already has a port named {name!r}")
    updated = replace(node, interfaces=(*node.interfaces, Interface(name)))
    return replace_node(project, updated), name
