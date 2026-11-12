import pytest

from homelab_maker.fields import (
    format_addresses,
    format_vlans,
    parse_addresses,
    parse_vlan,
    parse_vlans,
    split_items,
)


def test_a_list_may_be_separated_by_commas_semicolons_or_spaces() -> None:
    assert split_items("a, b;c  d,,") == ["a", "b", "c", "d"]
    assert split_items("   ") == []


def test_addresses_are_split_and_joined_back() -> None:
    assert parse_addresses("192.168.1.10/24, fd00::1/64") == ("192.168.1.10/24", "fd00::1/64")
    assert format_addresses(("10.0.0.1/8", "10.0.0.2/8")) == "10.0.0.1/8, 10.0.0.2/8"
    assert parse_addresses("") == ()


def test_a_vlan_is_a_number_or_nothing() -> None:
    assert parse_vlan(" 20 ") == 20
    assert parse_vlan("") is None


@pytest.mark.parametrize("text", ["abc", "0", "4095", "-3", "1.5"])
def test_a_bad_vlan_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="VLAN"):
        parse_vlan(text)


def test_vlan_lists_understand_ranges() -> None:
    assert parse_vlans("10, 20, 30-32") == (10, 20, 30, 31, 32)
    assert parse_vlans("32-30".replace("32-30", "30-30")) == (30,)
    assert parse_vlans("") == ()
    assert parse_vlans("5 5 5") == (5,)


@pytest.mark.parametrize("text", ["x", "10-", "5-3", "0", "4095", "1-4094999", "10-x"])
def test_a_bad_vlan_list_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        parse_vlans(text)


def test_formatting_vlans_reads_back_to_the_same_numbers() -> None:
    for vlans in [(), (7,), (10, 30, 31, 32), (1, 2, 3, 5, 7, 8), tuple(range(1, 101))]:
        assert parse_vlans(format_vlans(vlans)) == vlans
    assert format_vlans((10, 30, 31, 32)) == "10, 30-32"
