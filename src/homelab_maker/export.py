"""Writing the drawing out as something else: a Markdown page and a draw.io diagram.

Both are plain text, made the same way every time (no dates, no random ids), so an export
that is kept next to the infrastructure it describes diffs cleanly in git.

An image (PNG or SVG) needs the window, so that lives in ``gui``. Nothing here knows Qt.
"""

import xml.etree.ElementTree as ET
from collections.abc import Sequence

from homelab_maker import __version__
from homelab_maker.catalog import CATALOG
from homelab_maker.checks import Severity, run_checks
from homelab_maker.model import Medium, Node, Project
from homelab_maker.reachability import NOT_MODELLED, analyse_all

# ------------------------------------------------------------------------------ Markdown


def _cell(text: str) -> str:
    """Text safe to put in a Markdown table cell."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines


def _where(project: Project, node: Node) -> str:
    chain: list[str] = []
    current = node
    seen: set[str] = set()
    while current.parent is not None and current.id not in seen:
        seen.add(current.id)
        parent = project.node(current.parent)
        if parent is None:
            break
        chain.append(parent.name)
        current = parent
    return " / ".join(reversed(chain)) if chain else "—"


def to_markdown(project: Project) -> str:
    """The whole homelab as a Markdown page: inventory, cables, flows and what looks wrong."""
    names = {node.id: node.name for node in project.nodes}
    results = {r.flow: r for r in analyse_all(project)}
    findings = run_checks(project)

    out = [
        f"# {project.name}",
        "",
        f"Written by HomeLabMaker {__version__} from the drawing. What it says about reachability "
        "is about the drawing, not about the real network.",
        "",
        f"{len(project.nodes)} devices, {len(project.links)} links, {len(project.flows)} flows.",
        "",
        "## Devices",
        "",
    ]
    rows = []
    for node in project.nodes:
        kind = CATALOG.get(node.kind)
        addresses = "; ".join(
            f"{interface.name}: {', '.join(interface.addresses)}"
            for interface in node.interfaces
            if interface.addresses
        )
        services = ", ".join(f"{s.name} ({s.protocol.value}/{s.port})" for s in node.services)
        rows.append(
            [
                node.name,
                kind.label if kind else node.kind,
                _where(project, node),
                addresses,
                services,
            ]
        )
    out += (
        _table(["Device", "Kind", "Inside", "Addresses", "Services"], rows) if rows else ["None."]
    )

    out += ["", "## Links", ""]
    link_rows = [
        [
            f"{names.get(link.a.node, link.a.node)} ({link.a.interface})",
            f"{names.get(link.b.node, link.b.node)} ({link.b.interface})",
            link.medium.value,
        ]
        for link in project.links
    ]
    out += _table(["From", "To", "Medium"], link_rows) if link_rows else ["None."]

    out += ["", "## Flows", ""]
    flow_rows = []
    for flow in project.flows:
        result = results[flow.id]
        flow_rows.append(
            [
                names.get(flow.source, flow.source),
                names.get(flow.destination, flow.destination),
                f"{flow.protocol.value}/{flow.port}",
                "reachable" if result.reachable else "blocked",
                result.detail,
                flow.description,
            ]
        )
    out += (
        _table(["From", "To", "Port", "Result", "Detail", "What for"], flow_rows)
        if flow_rows
        else ["None."]
    )

    out += ["", "## Checks", ""]
    if findings:
        for finding in findings:
            label = "Warning" if finding.severity is Severity.WARNING else "Note"
            out.append(f"- {label}: {finding.message}")
    else:
        out.append("Nothing to report.")

    out += ["", "## What the analysis does not model", ""]
    out += [f"- {item}" for item in NOT_MODELLED]
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------------------- draw.io

# Size of a grid cell and of a device in a draw.io page, in its units (pixels).
_CELL_W, _CELL_H = 170, 120
_NODE_W, _NODE_H = 130, 70
_PAD = 20

_EDGE_STYLE = {
    Medium.ETHERNET: "endArrow=none;strokeWidth=2;",
    Medium.FIBER: "endArrow=none;strokeWidth=4;",
    Medium.WIFI: "endArrow=none;strokeWidth=2;dashed=1;dashPattern=1 3;",
    Medium.VPN: "endArrow=none;strokeWidth=2;dashed=1;",
}
_ZONE_COLOURS = (
    ("#dae8fc", "#6c8ebf"),
    ("#d5e8d4", "#82b366"),
    ("#fff2cc", "#d6b656"),
    ("#e1d5e7", "#9673a6"),
)


def _size(project: Project, node: Node) -> tuple[int, int]:
    """A device is a card, unless it holds others, and then it is as big as they need."""
    inside = project.children(node.id)
    if not inside:
        return _NODE_W, _NODE_H
    width = max(c.x for c in inside) + 1
    height = max(c.y for c in inside) + 1
    return (
        max(_NODE_W, width * _CELL_W + 2 * _PAD),
        max(_NODE_H, height * _CELL_H + _NODE_H),
    )


def to_drawio(project: Project) -> str:
    """The drawing as a diagrams.net (draw.io) file, to open and keep editing there."""
    model = ET.Element("mxGraphModel", {"grid": "1", "gridSize": "10", "page": "0"})
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    def vertex(
        cell_id: str, label: str, style: str, parent: str, x: int, y: int, w: int, h: int
    ) -> None:
        cell = ET.SubElement(
            root,
            "mxCell",
            {"id": cell_id, "value": label, "style": style, "vertex": "1", "parent": parent},
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"},
        )

    for index, zone in enumerate(project.zones):
        fill, line = _ZONE_COLOURS[index % len(_ZONE_COLOURS)]
        style = (
            f"rounded=1;dashed=1;fillColor={fill};strokeColor={line};opacity=50;"
            "verticalAlign=top;align=left;spacingLeft=8;fontStyle=1;"
        )
        vertex(
            f"z-{zone.id}",
            zone.name,
            style,
            "1",
            zone.x * _CELL_W,
            zone.y * _CELL_H,
            zone.width * _CELL_W,
            zone.height * _CELL_H,
        )

    # A host has to come before what is inside it, so parents are written first.
    ordered = sorted(project.nodes, key=lambda n: (_depth(project, n), n.id))
    for node in ordered:
        kind = CATALOG.get(node.kind)
        holds = bool(project.children(node.id))
        style = (
            "rounded=1;whiteSpace=wrap;html=0;"
            + ("container=1;collapsible=0;verticalAlign=top;" if holds else "")
            + f"strokeColor=#1b2230;fillColor={'#f5f5f5' if holds else '#ffffff'};"
        )
        label = f"{node.name} ({kind.label})" if kind else node.name
        width, height = _size(project, node)
        parent = f"n-{node.parent}" if node.parent else "1"
        inside_host = node.parent is not None
        x = node.x * _CELL_W + (_PAD if inside_host else 0)
        y = node.y * _CELL_H + (_NODE_H if inside_host else 0)
        vertex(f"n-{node.id}", label, style, parent, x, y, width, height)

    known = {node.id for node in project.nodes}
    for link in project.links:
        if link.a.node not in known or link.b.node not in known:
            continue
        value = f"{link.a.interface} to {link.b.interface}"
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": f"l-{link.id}",
                "value": value,
                "style": _EDGE_STYLE[link.medium] + "fontSize=10;",
                "edge": "1",
                "parent": "1",
                "source": f"n-{link.a.node}",
                "target": f"n-{link.b.node}",
            },
        )
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})

    file = ET.Element("mxfile", {"host": "HomeLabMaker"})
    diagram = ET.SubElement(file, "diagram", {"id": "homelab", "name": project.name})
    diagram.append(model)
    ET.indent(file)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(file, encoding="unicode") + "\n"


def _depth(project: Project, node: Node) -> int:
    depth, seen = 0, {node.id}
    current = node
    while current.parent is not None:
        parent = project.node(current.parent)
        if parent is None or parent.id in seen:
            break
        seen.add(parent.id)
        depth += 1
        current = parent
    return depth
