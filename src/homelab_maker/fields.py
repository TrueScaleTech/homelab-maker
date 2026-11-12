"""Turning what someone types into values, and values back into text.

The details panel offers text boxes; these functions decide what the text means. They raise
``ValueError`` with a message fit to show, and know nothing about Qt.
"""

import re

from homelab_maker.model import ANY, MAX_PORT, MAX_VLAN, Project, is_network

_SEPARATORS = re.compile(r"[,;\s]+")


def split_items(text: str) -> list[str]:
    """Split a comma, semicolon or space separated list, ignoring empty pieces."""
    return [piece for piece in _SEPARATORS.split(text.strip()) if piece]


def parse_addresses(text: str) -> tuple[str, ...]:
    """``"192.168.1.10/24, fd00::1/64"`` becomes a tuple. Validation is the model's."""
    return tuple(split_items(text))


def format_addresses(addresses: tuple[str, ...]) -> str:
    return ", ".join(addresses)


def parse_vlan(text: str) -> int | None:
    """One VLAN number, or nothing for the default VLAN."""
    text = text.strip()
    if not text:
        return None
    if not text.isdigit():
        raise ValueError(f"{text!r} is not a VLAN number")
    number = int(text)
    if not 1 <= number <= MAX_VLAN:
        raise ValueError(f"a VLAN is a number from 1 to {MAX_VLAN}")
    return number


def parse_vlans(text: str) -> tuple[int, ...]:
    """A list of VLANs with ranges: ``"10, 20, 30-32"`` is 10, 20, 30, 31 and 32."""
    found: set[int] = set()
    for piece in split_items(text):
        low, dash, high = piece.partition("-")
        try:
            first = int(low)
            last = int(high) if dash else first
        except ValueError:
            raise ValueError(f"{piece!r} is not a VLAN or a range such as 30-32") from None
        if first > last:
            raise ValueError(f"the range {piece!r} runs backwards")
        if first < 1 or last > MAX_VLAN:
            raise ValueError(f"a VLAN is a number from 1 to {MAX_VLAN}")
        if last - first > MAX_VLAN:
            raise ValueError(f"the range {piece!r} is too long")
        found.update(range(first, last + 1))
    return tuple(sorted(found))


def format_vlans(vlans: tuple[int, ...]) -> str:
    """The shortest text that reads back to the same VLANs: 10, 30, 31, 32 is ``10, 30-32``."""
    if not vlans:
        return ""
    pieces: list[str] = []
    start = previous = vlans[0]
    for number in (*vlans[1:], None):
        if number is not None and number == previous + 1:
            previous = number
            continue
        pieces.append(str(start) if start == previous else f"{start}-{previous}")
        if number is not None:
            start = previous = number
    return ", ".join(pieces)


def parse_reference(project: Project, text: str) -> str:
    """What a rule's source or destination means: ``any``, a network, or a device.

    A device may be written by its id or by its name, in any case.
    """
    text = text.strip()
    if not text:
        raise ValueError("write any, a network such as 192.168.1.0/24, or the name of a device")
    if text.lower() == ANY:
        return ANY
    if is_network(text):
        return text
    for node in project.nodes:
        if text == node.id or text.lower() == node.name.lower():
            return node.id
    raise ValueError(f"there is no device called {text!r}")


def parse_port(text: str) -> int | None:
    """A port number, or nothing for "any port"."""
    text = text.strip()
    if not text or text.lower() == ANY:
        return None
    if not text.isdigit() or not 1 <= int(text) <= MAX_PORT:
        raise ValueError(f"a port is a number from 1 to {MAX_PORT}")
    return int(text)
