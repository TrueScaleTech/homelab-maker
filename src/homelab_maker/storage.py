"""The project file: one JSON document, written to be read, diffed and committed.

Keys are sorted, the layout is fixed and collections are ordered by id, so the same
homelab always produces the same bytes. That makes a project diff cleanly in git.

A project file is data only. Loading it never executes anything, and it is read strictly:
an unknown field, a value of the wrong type or a reference to something that does not
exist is refused with a message that names where the problem is, instead of being guessed
at. A file from a newer format version, or larger than ``MAX_FILE_BYTES``, is refused too.
"""

import functools
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, TypeVar

from homelab_maker.model import (
    ANY,
    DEFAULT_PROJECT_NAME,
    Endpoint,
    Flow,
    Interface,
    InterfaceMode,
    Link,
    Medium,
    Node,
    Project,
    Protocol,
    Rule,
    RuleAction,
    RuleProtocol,
    Service,
    Zone,
)
from homelab_maker.validation import validate

FORMAT_VERSION = 1
MAX_FILE_BYTES = 5 * 1024 * 1024

T = TypeVar("T")


class ProjectFileError(Exception):
    """A project file cannot be used. The message is written for the person who opens it."""


# ------------------------------------------------------------------------------ writing


def dumps(project: Project) -> str:
    """The canonical text of ``project``."""
    data = {
        "format_version": FORMAT_VERSION,
        "name": project.name,
        "nodes": [_node_data(node) for node in project.nodes],
        "links": [_link_data(link) for link in project.links],
        "zones": [
            {"id": z.id, "name": z.name, "x": z.x, "y": z.y, "width": z.width, "height": z.height}
            for z in project.zones
        ],
        "flows": [
            {
                "id": f.id,
                "source": f.source,
                "destination": f.destination,
                "port": f.port,
                "protocol": f.protocol.value,
                "description": f.description,
            }
            for f in project.flows
        ],
    }
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def _node_data(node: Node) -> dict[str, object]:
    return {
        "id": node.id,
        "kind": node.kind,
        "name": node.name,
        "x": node.x,
        "y": node.y,
        "parent": node.parent,
        "routes": node.routes,
        "interfaces": [
            {
                "name": i.name,
                "addresses": list(i.addresses),
                "mode": i.mode.value,
                "vlan": i.vlan,
                "trunk_vlans": list(i.trunk_vlans),
            }
            for i in node.interfaces
        ],
        "services": [
            {"name": s.name, "port": s.port, "protocol": s.protocol.value} for s in node.services
        ],
        "rules": [
            {
                "action": r.action.value,
                "source": r.source,
                "destination": r.destination,
                "protocol": r.protocol.value,
                "port": r.port,
            }
            for r in node.rules
        ],
    }


def _link_data(link: Link) -> dict[str, object]:
    return {
        "id": link.id,
        "a": {"node": link.a.node, "interface": link.a.interface},
        "b": {"node": link.b.node, "interface": link.b.interface},
        "medium": link.medium.value,
        "speed_mbps": link.speed_mbps,
    }


def save(path: Path, project: Project) -> None:
    """Write ``project`` to ``path``. The old file stays intact unless the new one is complete.

    Raises ``OSError`` if the disk refuses.
    """
    text = dumps(project)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        # newline="\n" keeps the bytes identical on Windows, which keeps git diffs quiet.
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


# ------------------------------------------------------------------------------ reading

_MISSING = object()

_PROJECT_KEYS = frozenset({"format_version", "name", "nodes", "links", "zones", "flows"})
_NODE_KEYS = frozenset(
    {"id", "kind", "name", "x", "y", "parent", "routes", "interfaces", "services", "rules"}
)
_INTERFACE_KEYS = frozenset({"name", "addresses", "mode", "vlan", "trunk_vlans"})
_SERVICE_KEYS = frozenset({"name", "port", "protocol"})
_RULE_KEYS = frozenset({"action", "source", "destination", "protocol", "port"})
_LINK_KEYS = frozenset({"id", "a", "b", "medium", "speed_mbps"})
_ENDPOINT_KEYS = frozenset({"node", "interface"})
_ZONE_KEYS = frozenset({"id", "name", "x", "y", "width", "height"})
_FLOW_KEYS = frozenset({"id", "source", "destination", "port", "protocol", "description"})


class _Obj:
    """A JSON object that is read field by field, with every failure naming its place."""

    def __init__(self, value: object, path: str, keys: frozenset[str]) -> None:
        if not isinstance(value, dict):
            raise ProjectFileError(f"{path or 'the project'}: expected an object")
        unknown = sorted(set(value) - keys)
        if unknown:
            names = ", ".join(repr(name) for name in unknown)
            raise ProjectFileError(f"{path or 'the project'}: unknown field {names}")
        self._data: dict[str, object] = value
        self.path = path

    def _child(self, key: str) -> str:
        return f"{self.path}.{key}" if self.path else key

    def _wrong(self, key: str, expected: str) -> ProjectFileError:
        return ProjectFileError(f"{self._child(key)}: expected {expected}")

    def _raw(self, key: str, default: object) -> object:
        if key in self._data:
            return self._data[key]
        if default is _MISSING:
            raise ProjectFileError(f"{self.path or 'the project'}: missing the field {key!r}")
        return default

    def text(self, key: str, default: object = _MISSING) -> str:
        value = self._raw(key, default)
        if not isinstance(value, str):
            raise self._wrong(key, "text")
        return value

    def integer(self, key: str, default: object = _MISSING) -> int:
        value = self._raw(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise self._wrong(key, "a whole number")
        return value

    def optional_text(self, key: str) -> str | None:
        value = self._raw(key, None)
        if value is not None and not isinstance(value, str):
            raise self._wrong(key, "text or null")
        return value

    def optional_integer(self, key: str) -> int | None:
        value = self._raw(key, None)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise self._wrong(key, "a whole number or null")
        return value

    def optional_bool(self, key: str) -> bool | None:
        value = self._raw(key, None)
        if value is not None and not isinstance(value, bool):
            raise self._wrong(key, "true, false or null")
        return value

    def texts(self, key: str) -> tuple[str, ...]:
        items = self._list(key)
        strings = tuple(item for item in items if isinstance(item, str))
        if len(strings) != len(items):
            raise self._wrong(key, "a list of text")
        return strings

    def integers(self, key: str) -> tuple[int, ...]:
        items = self._list(key)
        numbers = tuple(
            item for item in items if isinstance(item, int) and not isinstance(item, bool)
        )
        if len(numbers) != len(items):
            raise self._wrong(key, "a list of whole numbers")
        return numbers

    def section(self, key: str, keys: frozenset[str]) -> "_Obj":
        return _Obj(self._raw(key, _MISSING), self._child(key), keys)

    def objects(self, key: str, keys: frozenset[str]) -> list["_Obj"]:
        return [
            _Obj(item, f"{self._child(key)}[{index}]", keys)
            for index, item in enumerate(self._list(key))
        ]

    def _list(self, key: str) -> list[object]:
        value = self._raw(key, [])
        if not isinstance(value, list):
            raise self._wrong(key, "a list")
        return value


def _make(path: str, build: Callable[[], T]) -> T:
    """Build a model value, turning its complaint into one that says where it is."""
    try:
        return build()
    except ValueError as exc:
        raise ProjectFileError(f"{path}: {exc}") from exc


def _read_all(objs: list[_Obj], reader: Callable[[_Obj], T]) -> tuple[T, ...]:
    return tuple(_make(obj.path, functools.partial(reader, obj)) for obj in objs)


def _read_interface(obj: _Obj) -> Interface:
    return Interface(
        name=obj.text("name"),
        addresses=obj.texts("addresses"),
        mode=InterfaceMode(obj.text("mode", InterfaceMode.ACCESS.value)),
        vlan=obj.optional_integer("vlan"),
        trunk_vlans=obj.integers("trunk_vlans"),
    )


def _read_service(obj: _Obj) -> Service:
    return Service(
        name=obj.text("name"),
        port=obj.integer("port"),
        protocol=Protocol(obj.text("protocol", Protocol.TCP.value)),
    )


def _read_rule(obj: _Obj) -> Rule:
    return Rule(
        action=RuleAction(obj.text("action")),
        source=obj.text("source", ANY),
        destination=obj.text("destination", ANY),
        protocol=RuleProtocol(obj.text("protocol", RuleProtocol.ANY.value)),
        port=obj.optional_integer("port"),
    )


def _read_node(obj: _Obj) -> Node:
    return Node(
        id=obj.text("id"),
        kind=obj.text("kind"),
        name=obj.text("name"),
        x=obj.integer("x", 0),
        y=obj.integer("y", 0),
        parent=obj.optional_text("parent"),
        routes=obj.optional_bool("routes"),
        interfaces=_read_all(obj.objects("interfaces", _INTERFACE_KEYS), _read_interface),
        services=_read_all(obj.objects("services", _SERVICE_KEYS), _read_service),
        rules=_read_all(obj.objects("rules", _RULE_KEYS), _read_rule),
    )


def _read_endpoint(obj: _Obj) -> Endpoint:
    return Endpoint(node=obj.text("node"), interface=obj.text("interface"))


def _read_link(obj: _Obj) -> Link:
    end_a = obj.section("a", _ENDPOINT_KEYS)
    end_b = obj.section("b", _ENDPOINT_KEYS)
    return Link(
        id=obj.text("id"),
        a=_make(end_a.path, functools.partial(_read_endpoint, end_a)),
        b=_make(end_b.path, functools.partial(_read_endpoint, end_b)),
        medium=Medium(obj.text("medium", Medium.ETHERNET.value)),
        speed_mbps=obj.optional_integer("speed_mbps"),
    )


def _read_zone(obj: _Obj) -> Zone:
    return Zone(
        id=obj.text("id"),
        name=obj.text("name"),
        x=obj.integer("x"),
        y=obj.integer("y"),
        width=obj.integer("width"),
        height=obj.integer("height"),
    )


def _read_flow(obj: _Obj) -> Flow:
    return Flow(
        id=obj.text("id"),
        source=obj.text("source"),
        destination=obj.text("destination"),
        port=obj.integer("port"),
        protocol=Protocol(obj.text("protocol", Protocol.TCP.value)),
        description=obj.text("description", ""),
    )


def _reject_constant(name: str) -> NoReturn:
    raise ProjectFileError(f"{name} is not a valid value in a project file")


def loads(text: str) -> Project:
    """Read a project from text. Raises ``ProjectFileError`` if it cannot be used."""
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ProjectFileError(
            f"not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}"
        ) from exc
    except RecursionError as exc:
        raise ProjectFileError("the file is nested too deeply to be a project") from exc

    if not isinstance(data, dict):
        raise ProjectFileError("the file does not hold a project: expected an object")
    version = data.get("format_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ProjectFileError("the file has no valid format_version, so it is not a project")
    if version > FORMAT_VERSION:
        raise ProjectFileError(
            f"this project uses file format {version}, but this version of HomeLabMaker "
            f"reads up to {FORMAT_VERSION}: update the application to open it"
        )

    root = _Obj(data, "", _PROJECT_KEYS)
    project = _make(
        "the project",
        lambda: Project(
            name=root.text("name", DEFAULT_PROJECT_NAME),
            nodes=_read_all(root.objects("nodes", _NODE_KEYS), _read_node),
            links=_read_all(root.objects("links", _LINK_KEYS), _read_link),
            zones=_read_all(root.objects("zones", _ZONE_KEYS), _read_zone),
            flows=_read_all(root.objects("flows", _FLOW_KEYS), _read_flow),
        ),
    )

    problems = validate(project)
    if problems:
        shown = "; ".join(problem.message for problem in problems[:3])
        more = f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""
        raise ProjectFileError(f"the project is inconsistent: {shown}{more}")
    return project


def load(path: Path) -> Project:
    """Read a project file. Raises ``ProjectFileError`` if it cannot be used."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        raise ProjectFileError(f"{path.name}: cannot be read ({exc.strerror or exc})") from exc
    if len(raw) > MAX_FILE_BYTES:
        limit = MAX_FILE_BYTES // (1024 * 1024)
        raise ProjectFileError(f"{path.name}: larger than the {limit} MiB limit for a project file")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProjectFileError(f"{path.name}: not a UTF-8 text file") from exc
    try:
        return loads(text)
    except ProjectFileError as exc:
        raise ProjectFileError(f"{path.name}: {exc}") from exc
