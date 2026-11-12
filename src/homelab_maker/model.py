"""The data model: plain, immutable values that describe a homelab.

Nothing here knows about the window, the disk or the network, so all of it is tested
without a display. Two layers of checking keep a model honest:

* each value checks itself when it is built (a VLAN outside 1-4094, a malformed address
  or a port of 70000 cannot be constructed at all);
* rules that span several values (a cable to a node that does not exist, a container
  inside a switch) are checked by ``validation.validate``.

Positions are whole grid cells. A node with no parent is placed on the canvas; a node
with a parent is placed relative to the content area of that parent, so moving a host
moves everything inside it.
"""

import contextlib
import ipaddress
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from homelab_maker.catalog import CATALOG

GRID_LIMIT = 10_000
MAX_VLAN = 4094
MAX_PORT = 65_535
MAX_SPEED_MBPS = 1_000_000
NAME_LIMIT = 80
INTERFACE_NAME_LIMIT = 32
DESCRIPTION_LIMIT = 200
DEFAULT_PROJECT_NAME = "Untitled homelab"

# The word that means "anything" in a rule, so no node may use it as an id.
ANY = "any"

_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}")


class Medium(StrEnum):
    ETHERNET = "ethernet"
    FIBER = "fiber"
    WIFI = "wifi"
    VPN = "vpn"


# A cable occupies its interface. Wireless and tunnel links share one.
PHYSICAL_MEDIA = frozenset({Medium.ETHERNET, Medium.FIBER})


class InterfaceMode(StrEnum):
    ACCESS = "access"
    TRUNK = "trunk"


class Protocol(StrEnum):
    TCP = "tcp"
    UDP = "udp"


class RuleAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class RuleProtocol(StrEnum):
    ANY = "any"
    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"


# ---------------------------------------------------------------------------- helpers


def _set(obj: object, name: str, value: object) -> None:
    """Assign a field of a frozen dataclass while it is still being built."""
    object.__setattr__(obj, name, value)


def _text(value: object, what: str, limit: int = NAME_LIMIT, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{what} must be text")
    if not allow_empty and not value.strip():
        raise ValueError(f"{what} must not be empty")
    if len(value) > limit:
        raise ValueError(f"{what} is longer than {limit} characters")
    if not value.isprintable():
        raise ValueError(f"{what} contains control characters")
    return value


def _integer(value: object, what: str, low: int, high: int) -> int:
    # bool is a subclass of int, and "true" is not a VLAN.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{what} must be a whole number")
    if not low <= value <= high:
        raise ValueError(f"{what} must be between {low} and {high}")
    return value


def _identifier(value: object, what: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(
            f"{what} {value!r} must be 1 to 63 characters: lowercase letters, digits, '-' and '_'"
        )
    return value


def _address(value: object) -> str:
    if isinstance(value, str):
        with contextlib.suppress(ValueError):
            return str(ipaddress.ip_interface(value))
    raise ValueError(f"{value!r} is not an IPv4 or IPv6 address with an optional prefix length")


def is_network(text: str) -> bool:
    """Whether ``text`` is a network such as ``192.168.1.0/24``."""
    try:
        ipaddress.ip_network(text, strict=False)
    except ValueError:
        return False
    return True


def _match(value: object) -> str:
    """A rule's source or destination: ``any``, a network, or the id of a node."""
    if isinstance(value, str):
        if value == ANY:
            return ANY
        try:
            return str(ipaddress.ip_network(value, strict=False))
        except ValueError:
            if _ID.fullmatch(value):
                return value
    raise ValueError(f"{value!r} must be 'any', a network such as 192.168.1.0/24, or a node id")


# ----------------------------------------------------------------------------- values


@dataclass(frozen=True, slots=True)
class Interface:
    """A named port on a node."""

    name: str
    addresses: tuple[str, ...] = ()
    mode: InterfaceMode = InterfaceMode.ACCESS
    # The untagged VLAN: the access VLAN, or the native VLAN of a trunk.
    vlan: int | None = None
    trunk_vlans: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _text(self.name, "interface name", INTERFACE_NAME_LIMIT)
        _set(self, "mode", InterfaceMode(self.mode))
        if self.vlan is not None:
            _integer(self.vlan, "VLAN", 1, MAX_VLAN)
        tagged = tuple(sorted({_integer(v, "VLAN", 1, MAX_VLAN) for v in self.trunk_vlans}))
        if tagged and self.mode is not InterfaceMode.TRUNK:
            raise ValueError("only a trunk interface can list tagged VLANs")
        _set(self, "trunk_vlans", tagged)
        addresses = tuple(_address(a) for a in self.addresses)
        if len(set(addresses)) != len(addresses):
            raise ValueError("an interface lists the same address twice")
        _set(self, "addresses", addresses)


@dataclass(frozen=True, slots=True)
class Service:
    """Something a node listens on."""

    name: str
    port: int
    protocol: Protocol = Protocol.TCP

    def __post_init__(self) -> None:
        _text(self.name, "service name", INTERFACE_NAME_LIMIT)
        _integer(self.port, "port", 1, MAX_PORT)
        _set(self, "protocol", Protocol(self.protocol))


@dataclass(frozen=True, slots=True)
class Rule:
    """One allow or deny entry on a node that forwards traffic. The first match wins."""

    action: RuleAction
    source: str = ANY
    destination: str = ANY
    protocol: RuleProtocol = RuleProtocol.ANY
    port: int | None = None

    def __post_init__(self) -> None:
        _set(self, "action", RuleAction(self.action))
        _set(self, "protocol", RuleProtocol(self.protocol))
        _set(self, "source", _match(self.source))
        _set(self, "destination", _match(self.destination))
        if self.port is not None:
            _integer(self.port, "port", 1, MAX_PORT)
            if self.protocol not in (RuleProtocol.TCP, RuleProtocol.UDP):
                raise ValueError("a port needs the protocol tcp or udp")


@dataclass(frozen=True, slots=True)
class Node:
    """A thing on the grid: a device, a virtual machine or a container."""

    id: str
    kind: str
    name: str
    x: int = 0
    y: int = 0
    parent: str | None = None
    interfaces: tuple[Interface, ...] = ()
    services: tuple[Service, ...] = ()
    rules: tuple[Rule, ...] = ()
    # None means "whatever the kind does".
    routes: bool | None = None

    def __post_init__(self) -> None:
        if _identifier(self.id, "node id") == ANY:
            raise ValueError(f"{ANY!r} is reserved and cannot be a node id")
        _identifier(self.kind, "device kind")
        _text(self.name, "node name")
        _integer(self.x, "x", -GRID_LIMIT, GRID_LIMIT)
        _integer(self.y, "y", -GRID_LIMIT, GRID_LIMIT)
        if self.parent is not None:
            _identifier(self.parent, "parent id")
        if self.routes is not None and not isinstance(self.routes, bool):
            raise ValueError("routes must be true, false or unset")
        _set(self, "interfaces", tuple(self.interfaces))
        _set(self, "services", tuple(self.services))
        _set(self, "rules", tuple(self.rules))


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One end of a link: an interface of a node."""

    node: str
    interface: str

    def __post_init__(self) -> None:
        _identifier(self.node, "node id")
        _text(self.interface, "interface name", INTERFACE_NAME_LIMIT)


@dataclass(frozen=True, slots=True)
class Link:
    """A cable or a wireless or tunnel link between two interfaces. It has no direction."""

    id: str
    a: Endpoint
    b: Endpoint
    medium: Medium = Medium.ETHERNET
    speed_mbps: int | None = None

    def __post_init__(self) -> None:
        _identifier(self.id, "link id")
        _set(self, "medium", Medium(self.medium))
        if self.speed_mbps is not None:
            _integer(self.speed_mbps, "speed", 1, MAX_SPEED_MBPS)
        # The same cable drawn from either end is the same link.
        if (self.b.node, self.b.interface) < (self.a.node, self.a.interface):
            first, second = self.b, self.a
            _set(self, "a", first)
            _set(self, "b", second)


@dataclass(frozen=True, slots=True)
class Zone:
    """A named rectangle on the grid that groups devices by purpose."""

    id: str
    name: str
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        _identifier(self.id, "zone id")
        _text(self.name, "zone name")
        _integer(self.x, "x", -GRID_LIMIT, GRID_LIMIT)
        _integer(self.y, "y", -GRID_LIMIT, GRID_LIMIT)
        _integer(self.width, "width", 1, GRID_LIMIT)
        _integer(self.height, "height", 1, GRID_LIMIT)


@dataclass(frozen=True, slots=True)
class Flow:
    """A statement that one node talks to a service of another."""

    id: str
    source: str
    destination: str
    port: int
    protocol: Protocol = Protocol.TCP
    description: str = ""

    def __post_init__(self) -> None:
        _identifier(self.id, "flow id")
        _identifier(self.source, "source node id")
        _identifier(self.destination, "destination node id")
        _integer(self.port, "port", 1, MAX_PORT)
        _set(self, "protocol", Protocol(self.protocol))
        _text(self.description, "description", DESCRIPTION_LIMIT, allow_empty=True)


@dataclass(frozen=True, slots=True)
class Project:
    """A whole homelab. Collections are kept sorted by id, so equal homelabs compare equal."""

    name: str = DEFAULT_PROJECT_NAME
    nodes: tuple[Node, ...] = ()
    links: tuple[Link, ...] = ()
    zones: tuple[Zone, ...] = ()
    flows: tuple[Flow, ...] = ()

    def __post_init__(self) -> None:
        _text(self.name, "project name")
        # sorted() is stable, so a duplicated id stays visible to the validation.
        _set(self, "nodes", tuple(sorted(self.nodes, key=lambda item: item.id)))
        _set(self, "links", tuple(sorted(self.links, key=lambda item: item.id)))
        _set(self, "zones", tuple(sorted(self.zones, key=lambda item: item.id)))
        _set(self, "flows", tuple(sorted(self.flows, key=lambda item: item.id)))

    def node(self, node_id: str) -> Node | None:
        return next((node for node in self.nodes if node.id == node_id), None)

    def children(self, parent_id: str | None) -> tuple[Node, ...]:
        """The nodes placed directly inside ``parent_id``, or on the canvas for ``None``."""
        return tuple(node for node in self.nodes if node.parent == parent_id)


# --------------------------------------------------------------------------- creating


def node_routes(node: Node) -> bool:
    """Whether a node forwards traffic between networks."""
    if node.routes is not None:
        return node.routes
    kind = CATALOG.get(node.kind)
    return kind is not None and kind.routes


def slugify(text: str) -> str:
    """Turn a display name into the start of an id."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")
    return slug or "item"


def unique_id(taken: Iterable[str], base: str) -> str:
    """``base`` if it is free, otherwise ``base-2``, ``base-3``, and so on."""
    used = set(taken)
    candidate = base
    number = 2
    while candidate in used:
        candidate = f"{base}-{number}"
        number += 1
    return candidate


def new_node(
    kind_key: str,
    name: str,
    taken_ids: Iterable[str],
    *,
    x: int = 0,
    y: int = 0,
    parent: str | None = None,
) -> Node:
    """A node of a catalogue kind with the interfaces that kind starts with."""
    kind = CATALOG.get(kind_key)
    if kind is None:
        raise ValueError(f"unknown device kind {kind_key!r}")
    return Node(
        id=unique_id(taken_ids, slugify(name)),
        kind=kind.key,
        name=name,
        x=x,
        y=y,
        parent=parent,
        interfaces=tuple(
            Interface(f"{kind.port_prefix}{number}") for number in range(1, kind.default_ports + 1)
        ),
    )
