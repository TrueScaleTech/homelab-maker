import re

from homelab_maker.catalog import CATALOG, Category


def test_every_key_is_a_valid_node_kind() -> None:
    # Node validates its kind as an identifier, so a catalogue key that fails it could
    # never be used.
    for key, kind in CATALOG.items():
        assert key == kind.key
        assert re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", key)


def test_containment_only_names_kinds_that_exist() -> None:
    for kind in CATALOG.values():
        assert kind.contains <= set(CATALOG), kind.key


def test_nesting_has_a_bottom() -> None:
    # Following "contains" can never loop, so nesting depth is always finite.
    def depth(key: str, trail: tuple[str, ...]) -> int:
        assert key not in trail, f"{key} can contain itself through {trail}"
        inner = CATALOG[key].contains
        return 1 + max((depth(child, (*trail, key)) for child in inner), default=0)

    for key in CATALOG:
        depth(key, ())


def test_only_virtual_kinds_are_ever_guests() -> None:
    guests = {child for kind in CATALOG.values() for child in kind.contains}
    assert guests == {key for key, kind in CATALOG.items() if kind.category is Category.VIRTUAL}


def test_only_forwarding_kinds_route() -> None:
    assert {key for key, kind in CATALOG.items() if kind.routes} == {"router", "firewall"}


def test_a_switch_starts_with_eight_ports() -> None:
    assert CATALOG["switch"].default_ports == 8
    assert CATALOG["switch"].port_prefix == "port"
