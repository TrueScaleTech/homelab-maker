"""The catalogue of device kinds: the single place that says what each kind is.

The model stores only a kind's key. What a kind may contain, how many interfaces a new
device of that kind starts with and whether it forwards traffic are all decided here, so
that the editor, the checks and the analysis can never disagree about them.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class Category(StrEnum):
    NETWORK = "network"
    HOST = "host"
    VIRTUAL = "virtual"
    ENDPOINT = "endpoint"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class DeviceKind:
    key: str
    label: str
    category: Category
    # Interfaces a new device of this kind starts with, named <port_prefix>1, 2, ...
    default_ports: int
    port_prefix: str
    # Forwards traffic between networks unless a node says otherwise.
    routes: bool = False
    # Passes other devices' traffic along (a switch, a modem, an access point, a router).
    # A device that does not is only ever the start or the end of a path.
    carries: bool = False
    # Kinds that may be placed directly inside this one.
    contains: frozenset[str] = frozenset()


_GUESTS = frozenset({"vm", "container"})

_KINDS = (
    DeviceKind("internet", "Internet", Category.EXTERNAL, 1, "eth"),
    DeviceKind("modem", "Modem or ONT", Category.NETWORK, 2, "eth", carries=True),
    DeviceKind("router", "Router", Category.NETWORK, 5, "eth", routes=True, carries=True),
    DeviceKind("firewall", "Firewall", Category.NETWORK, 4, "eth", routes=True, carries=True),
    DeviceKind("switch", "Switch", Category.NETWORK, 8, "port", carries=True),
    DeviceKind("access_point", "Access point", Category.NETWORK, 1, "eth", carries=True),
    DeviceKind("nas", "NAS", Category.HOST, 2, "eth", contains=_GUESTS),
    DeviceKind("server", "Server or mini PC", Category.HOST, 2, "eth", contains=_GUESTS),
    DeviceKind(
        "raspberry_pi", "Raspberry Pi", Category.HOST, 1, "eth", contains=frozenset({"container"})
    ),
    DeviceKind("workstation", "Desktop or laptop", Category.ENDPOINT, 1, "eth", contains=_GUESTS),
    DeviceKind(
        "vm", "Virtual machine", Category.VIRTUAL, 1, "vnic", contains=frozenset({"container"})
    ),
    DeviceKind("container", "Container", Category.VIRTUAL, 1, "veth"),
    DeviceKind("printer", "Printer", Category.ENDPOINT, 1, "eth"),
    DeviceKind("camera", "Camera", Category.ENDPOINT, 1, "eth"),
    DeviceKind("iot", "Smart device", Category.ENDPOINT, 1, "eth"),
)

CATALOG: Mapping[str, DeviceKind] = MappingProxyType({kind.key: kind for kind in _KINDS})
