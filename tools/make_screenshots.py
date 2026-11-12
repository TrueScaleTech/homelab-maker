"""Render the invented example homelab to PNG files for the README.

Usage:  python tools/make_screenshots.py OUTPUT_DIR [FONT_FILE]

It draws the real window on Qt's invisible platform, which has no fonts of its own, so
pass a TrueType font file (for instance C:\\Windows\\Fonts\\segoeui.ttf) or the labels come
out as empty boxes. Only the shipped example is ever drawn, never a real network.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# The window saves its preferences; keep this run away from the real ones.
os.environ["HOMELAB_MAKER_CONFIG_DIR"] = tempfile.mkdtemp(prefix="homelab-maker-shots-")

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from homelab_maker.gui.main_window import MainWindow
from homelab_maker.outage import what_goes_down

EXAMPLE = Path(__file__).parent.parent / "examples" / "small-homelab.homelab.json"
CAMERA_FLOW, DASHBOARD_FLOW = 0, 2  # rows of the flows table, which is sorted by id


def main(output: Path, font_file: Path | None) -> None:
    app = QApplication([])
    if font_file is not None:
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            raise SystemExit(f"could not load the font {font_file}")
        app.setFont(QFont(families[0], 9))

    window = MainWindow()
    window.resize(1500, 900)
    window.show()
    app.processEvents()
    if not window.open_path(EXAMPLE):
        raise SystemExit("could not open the example")
    output.mkdir(parents=True, exist_ok=True)

    def shoot(name: str) -> None:
        app.processEvents()
        target = output / f"{name}.png"
        if not window.grab().save(str(target)):
            raise SystemExit(f"could not write {target}")
        print(f"wrote {target}")

    def reset() -> None:
        window.canvas.set_offline(frozenset())
        window.flows_panel.table.clearSelection()
        window.canvas.go_to(None)
        window.canvas.select_ids(set())
        window.canvas.zoom_fit()

    for scheme in ("light", "dark"):
        window.set_scheme(scheme)  # type: ignore[arg-type]
        reset()
        window.canvas.select_ids({"nas"})
        window.checks_dock.raise_()
        shoot(f"overview-{scheme}")

    window.set_scheme("light")
    reset()
    window.canvas.select_ids({"switch"})
    window.inspector.tabs.setCurrentIndex(0)
    shoot("ports")

    reset()
    window.canvas.enter("nas")
    window.canvas.select_ids({"home-assistant"})
    window.inspector.tabs.setCurrentIndex(1)
    shoot("inside-a-host")

    reset()
    window.flows_dock.raise_()
    window.flows_panel.table.selectRow(CAMERA_FLOW)
    shoot("flow-blocked")

    reset()
    window.flows_dock.raise_()
    window.flows_panel.table.selectRow(DASHBOARD_FLOW)
    window.flows_panel.play_button.setChecked(True)
    window.canvas.advance_packet(0.55)
    shoot("flow-reachable")
    window.flows_panel.play_button.setChecked(False)

    reset()
    window.canvas.select_ids({"gateway"})
    window.inspector.tabs.setCurrentIndex(2)
    shoot("rules")

    reset()
    window.canvas.select_ids({"switch"})
    outage = what_goes_down(window.document.project, ["switch"])
    window.canvas.set_offline(frozenset(outage.stopped))
    window.checks_dock.raise_()
    shoot("what-goes-down")

    window.deleteLater()


if __name__ == "__main__":
    if not 2 <= len(sys.argv) <= 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) == 3 else None)
