"""The Markdown page and the draw.io file, and the buttons that write them."""

import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from homelab_maker import __version__
from homelab_maker.export import to_drawio, to_markdown
from homelab_maker.gui.main_window import MainWindow
from homelab_maker.model import Medium, Node, Project
from homelab_maker.operations import add_node, connect

# ---------------------------------------------------------------------------- Markdown


def test_the_page_has_every_section(sample: Project) -> None:
    page = to_markdown(sample)
    for heading in ("## Devices", "## Links", "## Flows", "## Checks", "## What the analysis"):
        assert heading in page
    assert page.startswith("# Small homelab (invented example)\n")
    assert page.endswith("\n") and not page.endswith("\n\n")


def test_the_page_says_where_things_are_and_how_the_flows_end(sample: Project) -> None:
    page = to_markdown(sample)
    assert "| Nextcloud | Container | TrueNAS / Docker host |" in page
    assert "| Hallway camera | TrueNAS | tcp/445 | blocked | Gateway denies it" in page
    assert "| Desktop | TrueNAS | tcp/443 | reachable | via Desktop" in page
    assert "SMB (tcp/445), Web UI (tcp/443)" in page


def test_the_page_lists_what_is_not_modelled(sample: Project) -> None:
    assert "- NAT and port forwarding" in to_markdown(sample)


def test_the_page_is_the_same_every_time(sample: Project) -> None:
    assert to_markdown(sample) == to_markdown(sample)
    assert __version__ in to_markdown(sample)


def test_an_empty_project_gives_a_page_that_says_none() -> None:
    page = to_markdown(Project())
    assert page.count("None.") == 3 and "Nothing to report." in page


def test_a_pipe_in_a_name_does_not_break_the_table() -> None:
    project = Project(nodes=(Node("a", "nas", "A | B"),))
    assert "| A \\| B |" in to_markdown(project)


def test_warnings_are_listed_as_warnings() -> None:
    project, _ = add_node(Project(), "nas", 0, 0)
    assert "- Warning: NAS has no cable or link" in to_markdown(project)


# ----------------------------------------------------------------------------- draw.io


def cells(text: str) -> dict[str, ET.Element]:
    root = ET.fromstring(text)
    assert root.tag == "mxfile"
    return {c.get("id", ""): c for c in root.iter("mxCell")}


def test_the_diagram_is_well_formed_and_has_every_part(sample: Project) -> None:
    found = cells(to_drawio(sample))
    assert {"0", "1"} <= found.keys()
    for node in sample.nodes:
        assert f"n-{node.id}" in found
    for link in sample.links:
        assert f"l-{link.id}" in found
    for zone in sample.zones:
        assert f"z-{zone.id}" in found


def test_the_ids_are_unique_and_every_edge_joins_two_cells(sample: Project) -> None:
    root = ET.fromstring(to_drawio(sample))
    ids = [c.get("id") for c in root.iter("mxCell")]
    assert len(ids) == len(set(ids))
    known = set(ids)
    for cell in root.iter("mxCell"):
        if cell.get("edge") == "1":
            assert cell.get("source") in known and cell.get("target") in known
        assert cell.get("parent") in known | {None}


def test_a_guest_is_a_child_of_its_host_and_the_host_is_a_container(sample: Project) -> None:
    found = cells(to_drawio(sample))
    assert found["n-home-assistant"].get("parent") == "n-nas"
    assert found["n-nextcloud"].get("parent") == "n-docker-host"
    assert "container=1" in (found["n-nas"].get("style") or "")
    assert "container=1" not in (found["n-switch"].get("style") or "")


def test_a_host_comes_before_what_is_inside_it(sample: Project) -> None:
    order = [c.get("id") for c in ET.fromstring(to_drawio(sample)).iter("mxCell")]
    assert order.index("n-nas") < order.index("n-docker-host") < order.index("n-nextcloud")


def test_each_medium_has_its_own_line_style() -> None:
    project, _ = add_node(Project(), "server", 0, 0)
    project, _ = add_node(project, "firewall", 4, 0)
    for medium in Medium:
        project, _ = connect(project, "server-or-mini-pc", "firewall", medium)
    styles = {
        c.get("style") for c in ET.fromstring(to_drawio(project)).iter("mxCell") if c.get("edge")
    }
    assert len(styles) == 4


def test_names_with_markup_are_escaped() -> None:
    project = Project(nodes=(Node("a", "nas", 'A & <b> "c"'),))
    text = to_drawio(project)
    assert "<b>" not in text
    assert cells(text)["n-a"].get("value") == 'A & <b> "c" (NAS)'


def test_a_link_to_a_missing_device_is_left_out(sample: Project) -> None:
    broken = replace(sample, nodes=tuple(n for n in sample.nodes if n.id != "camera"))
    found = cells(to_drawio(broken))
    assert "l-switch-camera" not in found


def test_an_empty_project_is_still_a_valid_file() -> None:
    assert set(cells(to_drawio(Project()))) == {"0", "1"}


# ----------------------------------------------------------------------------- buttons


class Chooser:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.path = ""
        self.starts: list[str] = []
        self.errors: list[str] = []

        def get_save_file_name(
            _parent: object, _title: str, start: str, _filter: str
        ) -> tuple[str, str]:
            self.starts.append(start)
            return self.path, ""

        monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(get_save_file_name))
        monkeypatch.setattr(
            QMessageBox, "critical", staticmethod(lambda _p, _t, text: self.errors.append(text))
        )


@pytest.fixture
def chooser(monkeypatch: pytest.MonkeyPatch) -> Chooser:
    return Chooser(monkeypatch)


@pytest.fixture
def shown(window: MainWindow, sample: Project) -> MainWindow:
    window.document.replace(sample, None)
    QApplication.processEvents()
    return window


def test_the_documentation_is_written_where_asked(
    shown: MainWindow, chooser: Chooser, tmp_path: Path
) -> None:
    chooser.path = str(tmp_path / "lab.md")
    shown.export_markdown_action.trigger()
    text = (tmp_path / "lab.md").read_text(encoding="utf-8")
    assert text.startswith("# Small homelab")
    assert b"\r" not in (tmp_path / "lab.md").read_bytes()


def test_a_name_with_no_suffix_gets_the_right_one(
    shown: MainWindow, chooser: Chooser, tmp_path: Path
) -> None:
    chooser.path = str(tmp_path / "lab")
    assert shown.export_drawio()
    assert ET.parse(tmp_path / "lab.drawio").getroot().tag == "mxfile"


def test_cancelling_a_dialog_writes_nothing(shown: MainWindow, chooser: Chooser) -> None:
    chooser.path = ""
    assert not shown.export_markdown() and not shown.export_drawio() and not shown.export_image()


def test_an_unwritable_place_is_reported(
    shown: MainWindow, chooser: Chooser, tmp_path: Path
) -> None:
    chooser.path = str(tmp_path / "missing-folder" / "lab.md")
    assert not shown.export_markdown()
    assert chooser.errors and "lab.md" in chooser.errors[0]


def test_a_png_is_a_real_image_of_the_drawing(
    shown: MainWindow, chooser: Chooser, tmp_path: Path
) -> None:
    chooser.path = str(tmp_path / "lab.png")
    assert shown.export_image()
    data = (tmp_path / "lab.png").read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) > 5000


def test_an_svg_is_a_real_vector_image(shown: MainWindow, chooser: Chooser, tmp_path: Path) -> None:
    chooser.path = str(tmp_path / "lab.svg")
    assert shown.export_image()
    text = (tmp_path / "lab.svg").read_text(encoding="utf-8")
    assert "<svg" in text and "Small homelab (invented example)" in text


def test_exporting_does_not_lose_the_selection(
    shown: MainWindow, chooser: Chooser, tmp_path: Path
) -> None:
    shown.canvas.select_ids({"nas"})
    chooser.path = str(tmp_path / "lab.png")
    shown.export_image()
    assert shown.canvas.selected_ids() == ["nas"]


def test_an_image_of_an_empty_homelab_is_still_written(
    window: MainWindow, chooser: Chooser, tmp_path: Path
) -> None:
    chooser.path = str(tmp_path / "empty.png")
    assert window.export_image()
    assert (tmp_path / "empty.png").stat().st_size > 0


def test_only_png_and_svg_are_images(window: MainWindow, chooser: Chooser, tmp_path: Path) -> None:
    chooser.path = str(tmp_path / "lab.bmp")
    assert not window.export_image()
    assert chooser.errors and "png or .svg" in chooser.errors[0]


def test_an_image_that_cannot_be_written_is_reported(
    shown: MainWindow, chooser: Chooser, tmp_path: Path
) -> None:
    chooser.path = str(tmp_path / "nowhere" / "lab.png")
    assert not shown.export_image()
    assert chooser.errors


def test_the_image_shows_what_the_view_shows(
    shown: MainWindow, chooser: Chooser, tmp_path: Path
) -> None:
    shown.canvas.enter("nas")
    chooser.path = str(tmp_path / "inside.png")
    assert shown.export_image()
    inside = (tmp_path / "inside.png").stat().st_size
    shown.canvas.leave()
    chooser.path = str(tmp_path / "outside.png")
    shown.export_image()
    assert inside != (tmp_path / "outside.png").stat().st_size


def test_exporting_uses_the_name_of_the_open_file(
    shown: MainWindow, chooser: Chooser, tmp_path: Path
) -> None:
    shown.document.mark_saved(tmp_path / "garage.homelab.json")
    shown.export_markdown()
    assert chooser.starts and chooser.starts[0].endswith("garage.md")
