"""Starting the application."""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from homelab_maker import __version__
from homelab_maker.viewmodel import APP_NAME

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="homelabmaker", description=f"{APP_NAME}: draw your homelab."
    )
    parser.add_argument("project", nargs="?", type=Path, help="a .homelab.json file to open")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument(
        "--smoke-test",
        type=Path,
        metavar="FILE",
        help="build a small homelab, save it to FILE, read it back and exit (build check)",
    )
    return parser


def _application() -> "QApplication":
    """The running application object, or a new one if there is none yet."""
    from PySide6.QtWidgets import QApplication

    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    return QApplication(sys.argv[:1])


def smoke_test(target: Path) -> int:
    """Start the real window without showing it, make a small homelab, and save and reload it.

    Returns 0 only if the file written can be read back as the same project.
    """
    from homelab_maker.gui.main_window import MainWindow
    from homelab_maker.storage import ProjectFileError, load, save

    # The window needs an application object alive; it is kept in a name so it is not freed.
    app = _application()
    window = MainWindow()
    window.canvas.add_device("switch", 0, 0)
    window.canvas.add_device("nas", 2, 0)
    window.canvas.add_device("workstation", 4, 0)
    project = window.document.project
    # No dialogs here: a build check must never wait for someone to click.
    try:
        save(target, project)
        reread = load(target)
    except (OSError, ProjectFileError):
        return 1
    finally:
        window.deleteLater()
        app.processEvents()
    return 0 if reread == project and len(reread.nodes) == 3 else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.smoke_test is not None:
        return smoke_test(args.smoke_test)

    from homelab_maker.gui import qt_theme
    from homelab_maker.gui.main_window import MainWindow

    app = _application()
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("TrueScaleTech")
    window = MainWindow()
    qt_theme.apply(app, window.tokens)
    window.show()
    if args.project is not None:
        window.open_path(args.project)
    return app.exec()
