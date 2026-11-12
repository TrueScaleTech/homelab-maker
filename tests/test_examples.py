import ipaddress
from pathlib import Path

import pytest

from homelab_maker.storage import dumps, load
from homelab_maker.validation import validate

EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.homelab.json"))


def test_there_is_at_least_one_example() -> None:
    assert EXAMPLES


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_an_example_loads_and_is_consistent(path: Path) -> None:
    assert validate(load(path)) == []


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_an_example_is_already_in_canonical_form(path: Path) -> None:
    # An example that is rewritten by a save would show up as a diff for no reason.
    assert path.read_text(encoding="utf-8") == dumps(load(path))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_an_example_holds_only_invented_addresses(path: Path) -> None:
    # Documentation (203.0.113.0/24) and private ranges only: no address of a real network.
    project = load(path)
    for node in project.nodes:
        for interface in node.interfaces:
            for address in interface.addresses:
                ip = ipaddress.ip_interface(address).ip
                assert ip.is_private, (
                    f"{node.id}: {address} is not a private or documentation address"
                )
