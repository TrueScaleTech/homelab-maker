"""Test setup shared by every test file."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Qt draws on an invisible platform, so the suite needs no screen. This has to be set
# before any test creates a Qt application.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from homelab_maker.gui.main_window import MainWindow
from homelab_maker.model import Project
from homelab_maker.settings import CONFIG_DIR_VARIABLE
from homelab_maker.storage import load

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture(autouse=True)
def private_preferences(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No test reads or writes the real preferences of whoever runs the suite."""
    config = tmp_path / "config"
    monkeypatch.setenv(CONFIG_DIR_VARIABLE, str(config))
    return config


@pytest.fixture
def sample() -> Project:
    """The shipped example: invented devices that use every part of the model."""
    return load(EXAMPLES / "small-homelab.homelab.json")


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    return app


@pytest.fixture
def window(qapp: QApplication) -> Iterator[MainWindow]:
    """A real main window on a blank document, shown on the invisible platform."""
    win = MainWindow()
    win.resize(1100, 700)
    win.show()
    qapp.processEvents()
    yield win
    # Close what was opened: widgets that pile up make the whole suite slow. The window is
    # not closed with close(), which would ask about unsaved changes.
    win.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
