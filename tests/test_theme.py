import pytest

from homelab_maker.gui.theme import DARK, LIGHT, Tokens, choose, contrast, luminance


def test_contrast_has_its_known_extremes() -> None:
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#777777") == pytest.approx(1.0)
    assert luminance("#000000") == 0.0
    assert luminance("#ffffff") == pytest.approx(1.0)


def test_contrast_does_not_depend_on_the_order() -> None:
    assert contrast("#123456", "#fedcba") == contrast("#fedcba", "#123456")


@pytest.mark.parametrize("tokens", [LIGHT, DARK], ids=lambda t: t.name)
def test_text_is_readable_on_everything_it_is_drawn_on(tokens: Tokens) -> None:
    for text in (tokens.text, tokens.text_muted):
        for surface in (tokens.card, tokens.background):
            assert contrast(text, surface) >= 4.5, (tokens.name, text, surface)


@pytest.mark.parametrize("tokens", [LIGHT, DARK], ids=lambda t: t.name)
def test_marks_that_are_not_text_stand_out_from_their_background(tokens: Tokens) -> None:
    # WCAG asks for 3:1 for graphics and interface parts.
    assert contrast(tokens.accent, tokens.background) >= 3
    assert contrast(tokens.accent, tokens.card) >= 3
    assert contrast(tokens.link, tokens.background) >= 3
    assert contrast(tokens.danger, tokens.card) >= 4.5


@pytest.mark.parametrize("tokens", [LIGHT, DARK], ids=lambda t: t.name)
def test_the_grid_is_quiet_but_visible(tokens: Tokens) -> None:
    assert 1.02 <= contrast(tokens.grid_minor, tokens.background) < 1.5
    assert contrast(tokens.grid_major, tokens.background) > contrast(
        tokens.grid_minor, tokens.background
    )


@pytest.mark.parametrize("tokens", [LIGHT, DARK], ids=lambda t: t.name)
def test_every_colour_is_a_plain_hex_value(tokens: Tokens) -> None:
    colours = [
        tokens.background,
        tokens.grid_minor,
        tokens.grid_major,
        tokens.card,
        tokens.card_border,
        tokens.text,
        tokens.text_muted,
        tokens.accent,
        tokens.danger,
        tokens.link,
        *tokens.zones,
    ]
    for colour in colours:
        assert len(colour) == 7
        assert colour.startswith("#")
        int(colour[1:], 16)
    assert 0 < tokens.zone_alpha < 128


def test_the_scheme_picks_the_tokens() -> None:
    assert choose("light", system_is_dark=True) is LIGHT
    assert choose("dark", system_is_dark=False) is DARK
    assert choose("system", system_is_dark=True) is DARK
    assert choose("system", system_is_dark=False) is LIGHT
