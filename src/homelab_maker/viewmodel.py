"""What the window shows, decided without the window.

Wording, counts and which links to draw live here, not in the widgets, so they are tested
without a display. The widgets only draw what these functions return.
"""

from dataclasses import dataclass
from pathlib import Path

from homelab_maker.model import Link, Medium, Project
from homelab_maker.operations import interface_links

APP_NAME = "HomeLabMaker"
PROJECT_SUFFIX = ".homelab.json"


def project_path(chosen: Path) -> Path:
    """The path a project is saved to: whatever the user typed, ending in ``.homelab.json``."""
    name = chosen.name
    if name.endswith(PROJECT_SUFFIX):
        return chosen
    if name.lower().endswith(".json"):
        name = name[: -len(".json")]
    return chosen.with_name(name + PROJECT_SUFFIX)


def window_title(path: Path | None, dirty: bool) -> str:
    name = path.name if path is not None else "Untitled"
    return f"{'*' if dirty else ''}{name} — {APP_NAME}"


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def status_text(project: Project, selected: int) -> str:
    parts = [
        _plural(len(project.nodes), "device", "devices"),
        _plural(len(project.links), "link", "links"),
    ]
    if selected:
        parts.append(f"{selected} selected")
    return " · ".join(parts)


def root_of(project: Project, node_id: str) -> str | None:
    """The id of the outermost host that contains ``node_id`` (itself if it has none)."""
    node = project.node(node_id)
    seen: set[str] = set()
    while node is not None and node.parent is not None and node.id not in seen:
        seen.add(node.id)
        parent = project.node(node.parent)
        if parent is None:
            break
        node = parent
    return node.id if node is not None else None


def inside_count(project: Project, node_id: str) -> int:
    """How many nodes sit inside ``node_id``, at any depth."""
    found: set[str] = set()
    frontier = [node_id]
    while frontier:
        current = frontier.pop()
        for child in project.children(current):
            if child.id not in found:
                found.add(child.id)
                frontier.append(child.id)
    return len(found)


def shown_as(project: Project, node_id: str, view: str | None) -> str | None:
    """The card, among those drawn inside ``view``, that stands for ``node_id``.

    That is the node itself when it sits directly in ``view``, or the host in ``view`` that
    contains it, at any depth. ``None`` when the node is not inside ``view`` at all.
    """
    node = project.node(node_id)
    seen: set[str] = set()
    while node is not None and node.id not in seen:
        if node.parent == view:
            return node.id
        seen.add(node.id)
        node = project.node(node.parent) if node.parent is not None else None
    return None


def trail(project: Project, view: str | None) -> tuple[tuple[str | None, str], ...]:
    """The way down from the canvas to ``view``: ``(id, name)`` pairs, the canvas first."""
    names: list[tuple[str | None, str]] = []
    node = project.node(view) if view is not None else None
    seen: set[str] = set()
    while node is not None and node.id not in seen:
        seen.add(node.id)
        names.append((node.id, node.name))
        node = project.node(node.parent) if node.parent is not None else None
    return ((None, project.name), *reversed(names))


def trail_text(project: Project, view: str | None) -> str:
    return " / ".join(name for _, name in trail(project, view))


@dataclass(frozen=True, slots=True)
class DrawnLink:
    """A link as the canvas draws it: between the cards at its two ends."""

    id: str
    a: str
    b: str
    medium: Medium


def drawn_links(project: Project, view: str | None = None) -> tuple[DrawnLink, ...]:
    """The links to draw inside ``view``.

    A link whose end is in a host is drawn to that host's card. A link with an end outside
    the view, or both ends on one card, is not drawn.
    """
    drawn = []
    for link in project.links:
        a, b = shown_as(project, link.a.node, view), shown_as(project, link.b.node, view)
        if a is not None and b is not None and a != b:
            drawn.append(DrawnLink(link.id, a, b, link.medium))
    return tuple(drawn)


@dataclass(frozen=True, slots=True)
class PortRow:
    """One interface of a node as the details panel lists it."""

    name: str
    addresses: tuple[str, ...]
    mode: str
    vlan: int | None
    tagged: tuple[int, ...]
    # The links on this interface, and who is at their other end ("Switch · port3").
    links: tuple[str, ...]
    peers: str


def _other_end(project: Project, link: Link, node_id: str, interface: str) -> str:
    end = link.b if (link.a.node, link.a.interface) == (node_id, interface) else link.a
    peer = project.node(end.node)
    return f"{peer.name if peer else end.node} · {end.interface}"


def port_rows(project: Project, node_id: str) -> tuple[PortRow, ...]:
    node = project.node(node_id)
    if node is None:
        return ()
    rows = []
    for interface in node.interfaces:
        links = interface_links(project, node_id, interface.name)
        rows.append(
            PortRow(
                name=interface.name,
                addresses=interface.addresses,
                mode=interface.mode.value,
                vlan=interface.vlan,
                tagged=interface.trunk_vlans,
                links=tuple(link.id for link in links),
                peers=", ".join(
                    _other_end(project, link, node_id, interface.name) for link in links
                ),
            )
        )
    return tuple(rows)


def link_summary(project: Project, link_id: str) -> str:
    """One line describing a cable: ``Switch · port3 — NAS · eth1 (ethernet)``."""
    link = next((item for item in project.links if item.id == link_id), None)
    if link is None:
        return ""
    ends = []
    for end in (link.a, link.b):
        node = project.node(end.node)
        ends.append(f"{node.name if node else end.node} · {end.interface}")
    return f"{ends[0]} — {ends[1]} ({link.medium.value})"
