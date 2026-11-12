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

EXAMPLE = Path(__file__).parent.parent / "examples" / "small-homelab.homelab.json"


def main(output: Path, font_file: Path | None) -> None:
    app = QApplication([])
    if font_file is not None:
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            raise SystemExit(f"could not load the font {font_file}")
        app.setFont(QFont(families[0], 9))

    window = MainWindow()
    window.resize(1280, 760)
    window.show()
    app.processEvents()
    if not window.open_path(EXAMPLE):
        raise SystemExit("could not open the example")
    window.canvas.select_ids({"nas"})
    output.mkdir(parents=True, exist_ok=True)
    for scheme in ("light", "dark"):
        window.set_scheme(scheme)  # type: ignore[arg-type]
        window.canvas.zoom_fit()
        app.processEvents()
        target = output / f"homelabmaker-{scheme}.png"
        if not window.grab().save(str(target)):
            raise SystemExit(f"could not write {target}")
        print(f"wrote {target}")
    window.deleteLater()


if __name__ == "__main__":
    if not 2 <= len(sys.argv) <= 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) == 3 else None)
