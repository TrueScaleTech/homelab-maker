import runpy
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from homelab_maker import __version__, app
from homelab_maker.catalog import CATALOG
from homelab_maker.gui.icons import (
    app_icon,
    app_image,
    has_glyph,
    kind_icon,
    paint_kind,
    render_kind,
)
from homelab_maker.gui.main_window import MainWindow
from homelab_maker.gui.palette import MIME_KIND, Palette
from homelab_maker.gui.theme import DARK, LIGHT
from homelab_maker.model import Project
from homelab_maker.storage import dumps, load

# ---------------------------------------------------------------------------- icons


def ink(image: QImage) -> int:
    """How many pixels the drawing touched."""
    return sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 0
    )


def test_every_kind_in_the_catalogue_has_its_own_glyph() -> None:
    assert [key for key in CATALOG if not has_glyph(key)] == []


@pytest.mark.parametrize("size", [16, 24, 32, 48, 96])
@pytest.mark.parametrize("key", list(CATALOG))
def test_every_glyph_draws_something_at_every_size(key: str, size: int) -> None:
    assert ink(render_kind(key, QColor("#000000"), size)) > size


def test_an_icon_takes_the_colour_it_is_given() -> None:
    light, dark = QColor(LIGHT.text), QColor(DARK.text)
    for colour in (light, dark):
        image = render_kind("nas", colour, 64)
        centre = [
            image.pixelColor(x, y)
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() == 255
        ]
        assert centre
        assert all(
            (c.red(), c.green(), c.blue()) == (colour.red(), colour.green(), colour.blue())
            for c in centre
        )


def test_glyphs_differ_from_one_another() -> None:
    images = {key: render_kind(key, QColor("#000000"), 48) for key in CATALOG}
    keys = list(images)
    for first in range(len(keys)):
        for second in range(first + 1, len(keys)):
            assert images[keys[first]] != images[keys[second]], (keys[first], keys[second])


def test_a_kind_without_a_glyph_still_gets_a_mark() -> None:
    assert not has_glyph("toaster")
    assert ink(render_kind("toaster", QColor("#000000"), 48)) > 0


def test_a_glyph_is_drawn_inside_the_rectangle_it_is_given() -> None:
    image = QImage(96, 96, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    paint_kind(painter, "router", QRectF(24, 24, 48, 48), QColor("#000000"))
    painter.end()
    for x in range(96):
        for y in range(96):
            if image.pixelColor(x, y).alpha() > 0:
                assert 22 <= x <= 74 and 22 <= y <= 74, (x, y)


def test_the_application_icon_is_a_rounded_tile_with_something_on_it(qapp: QApplication) -> None:
    image = app_image(256)
    assert image.size().width() == 256
    assert image.pixelColor(0, 0).alpha() == 0  # the corners are rounded away
    assert image.pixelColor(128, 8).alpha() == 255  # the tile itself is solid
    white = sum(
        1 for x in range(0, 256, 4) for y in range(0, 256, 4) if image.pixelColor(x, y).red() > 200
    )
    assert white > 20  # the network drawn on it
    assert not app_icon().isNull()


def test_the_icon_can_be_written_for_the_windows_build(tmp_path: Path, qapp: QApplication) -> None:
    target = tmp_path / "homelab-maker.ico"
    assert app_image().save(str(target))
    assert target.stat().st_size > 100


# --------------------------------------------------------------------------- palette


def test_the_list_offers_every_kind_in_catalogue_order(qapp: QApplication) -> None:
    palette = Palette(LIGHT)
    try:
        keys = [
            str(palette.item(row).data(Qt.ItemDataRole.UserRole)) for row in range(palette.count())
        ]
        labels = [palette.item(row).text() for row in range(palette.count())]
        assert keys == list(CATALOG)
        assert labels == [kind.label for kind in CATALOG.values()]
        assert all(not palette.item(row).icon().isNull() for row in range(palette.count()))
    finally:
        palette.deleteLater()


def test_a_drag_carries_the_kind_as_text(qapp: QApplication) -> None:
    palette = Palette(LIGHT)
    try:
        data = palette.mimeData([palette.item(6)])
        assert bytes(data.data(MIME_KIND).data()) == b"nas"
        assert palette.mimeTypes() == [MIME_KIND]
        assert palette.mimeData([]).formats() == []
    finally:
        palette.deleteLater()


def test_activating_a_kind_announces_it(qapp: QApplication) -> None:
    palette = Palette(LIGHT)
    heard: list[str] = []
    palette.kind_chosen.connect(heard.append)
    try:
        palette.itemActivated.emit(palette.item(4))
        assert heard == ["switch"]
    finally:
        palette.deleteLater()


def test_the_icons_follow_the_theme(qapp: QApplication) -> None:
    palette = Palette(LIGHT)
    try:
        before = palette.item(0).icon().pixmap(26, 26).toImage()
        palette.set_tokens(DARK)
        assert palette.item(0).icon().pixmap(26, 26).toImage() != before
    finally:
        palette.deleteLater()


# ------------------------------------------------------------------------------ app


def test_the_smoke_test_builds_saves_and_rereads_a_homelab(
    tmp_path: Path, qapp: QApplication
) -> None:
    target = tmp_path / "smoke.homelab.json"
    assert app.smoke_test(target) == 0
    assert sorted(n.kind for n in load(target).nodes) == ["nas", "switch", "workstation"]


def test_the_smoke_test_fails_instead_of_hanging_when_it_cannot_write(
    tmp_path: Path, qapp: QApplication
) -> None:
    assert app.smoke_test(tmp_path / "missing-folder" / "smoke.homelab.json") == 1


def test_main_runs_the_smoke_test_when_asked(tmp_path: Path, qapp: QApplication) -> None:
    target = tmp_path / "smoke.homelab.json"
    assert app.main(["--smoke-test", str(target)]) == 0
    assert target.is_file()


def test_the_version_flag_prints_the_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        app.main(["--version"])
    assert stop.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_the_command_line_takes_an_optional_project() -> None:
    parser = app._parser()
    assert parser.parse_args([]).project is None
    assert parser.parse_args(["lab.homelab.json"]).project == Path("lab.homelab.json")
    assert parser.parse_args(["--smoke-test", "out.json"]).smoke_test == Path("out.json")


def test_kind_icons_are_real_icons(qapp: QApplication) -> None:
    assert not kind_icon("nas", QColor("#000000")).isNull()


def test_the_application_opens_the_project_it_is_given_and_runs_until_quit(
    tmp_path: Path, qapp: QApplication, sample: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "lab.homelab.json"
    target.write_text(dumps(sample), encoding="utf-8")
    opened: list[Path] = []
    original = MainWindow.open_path

    def spy(self: MainWindow, path: Path) -> bool:
        opened.append(path)
        return original(self, path)

    monkeypatch.setattr(MainWindow, "open_path", spy)
    QTimer.singleShot(100, qapp.quit)
    assert app.main([str(target)]) == 0
    assert opened == [target]


def test_the_application_starts_with_a_blank_document_and_quits(qapp: QApplication) -> None:
    QTimer.singleShot(100, qapp.quit)
    assert app.main([]) == 0


def test_python_dash_m_starts_the_same_entry_point(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["homelabmaker", "--version"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("homelab_maker", run_name="__main__")
    assert stop.value.code == 0
    assert __version__ in capsys.readouterr().out
