"""What the window shows, decided without the window.

Wording, counts and which links to draw live here, not in the widgets, so they are tested
without a display. The widgets only draw what these functions return.
"""

from dataclasses import dataclass
from pathlib import Path

from homelab_maker.model import Medium, Project

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


@dataclass(frozen=True, slots=True)
class DrawnLink:
    """A link as the canvas draws it: between the outermost hosts at its two ends."""

    id: str
    a: str
    b: str
    medium: Medium


def drawn_links(project: Project) -> tuple[DrawnLink, ...]:
    """The links to draw. A cable inside a host, or to a node that is missing, is not drawn."""
    drawn = []
    for link in project.links:
        a, b = root_of(project, link.a.node), root_of(project, link.b.node)
        if a is not None and b is not None and a != b:
            drawn.append(DrawnLink(link.id, a, b, link.medium))
    return tuple(drawn)
