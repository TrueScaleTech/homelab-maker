from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox

from homelab_maker import __version__, settings
from homelab_maker.document import Document
from homelab_maker.gui.main_window import MainWindow
from homelab_maker.gui.theme import DARK, LIGHT
from homelab_maker.model import Project
from homelab_maker.storage import dumps, load

SUFFIX = ".homelab.json"


class Dialogs:
    """Stands in for the modal dialogs, so a test can say what the user would answer."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.questions = 0
        self.errors: list[str] = []
        self.answer = QMessageBox.StandardButton.Cancel
        self.open_as: str = ""
        self.save_as: str = ""
        self.about_text = ""

        def question(*args: object) -> QMessageBox.StandardButton:
            self.questions += 1
            return self.answer

        def critical(_parent: object, title: str, text: str) -> None:
            self.errors.append(f"{title}: {text}")

        def about(_parent: object, title: str, text: str) -> None:
            self.about_text = f"{title} {text}"

        monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
        monkeypatch.setattr(QMessageBox, "critical", staticmethod(critical))
        monkeypatch.setattr(QMessageBox, "about", staticmethod(about))
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (self.open_as, ""))
        )
        monkeypatch.setattr(
            QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (self.save_as, ""))
        )


@pytest.fixture
def dialogs(monkeypatch: pytest.MonkeyPatch) -> Dialogs:
    return Dialogs(monkeypatch)


# ------------------------------------------------------------------------- the title


def test_a_new_window_is_untitled_and_clean(window: MainWindow) -> None:
    assert window.windowTitle() == "Untitled — HomeLabMaker"
    assert not window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()
    assert not window.delete_action.isEnabled()
    assert not window.rename_action.isEnabled()


def test_a_change_marks_the_title_and_enables_undo(window: MainWindow) -> None:
    window.canvas.add_device("nas", 1, 1)
    assert window.windowTitle().startswith("*Untitled")
    assert window.undo_action.isEnabled()
    assert window.undo_action.text() == "&Undo Add nas"
    assert window.delete_action.isEnabled()
    assert window.rename_action.isEnabled()  # the new device is selected


def test_undo_and_redo_go_through_the_menu_actions(window: MainWindow) -> None:
    window.canvas.add_device("nas", 1, 1)
    window.undo_action.trigger()
    assert window.document.project == Project()
    assert window.redo_action.isEnabled()
    assert window.redo_action.text() == "&Redo Add nas"
    window.redo_action.trigger()
    assert len(window.document.project.nodes) == 1


def test_control_z_undoes_from_the_keyboard(window: MainWindow, qapp: QApplication) -> None:
    window.activateWindow()
    qapp.processEvents()
    window.canvas.add_device("nas", 1, 1)
    window.canvas.setFocus()
    QTest.keyClick(window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window.document.project == Project()


def test_the_status_bar_counts_what_is_there(window: MainWindow) -> None:
    window.canvas.add_device("nas", 1, 1)
    window.canvas.add_device("switch", 3, 1)
    assert window._counts.text() == "2 devices · 0 links · 1 selected"


def test_double_clicking_in_the_list_places_a_device_in_view(window: MainWindow) -> None:
    item = window.device_list.item(4)  # the switch
    viewport = window.device_list.viewport()
    pos = window.device_list.visualItemRect(item).center()
    # A double click is always preceded by the first click of the pair.
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
    QTest.mouseDClick(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
    assert [n.kind for n in window.document.project.nodes] == ["switch"]
    assert (
        window.canvas.viewport()
        .rect()
        .contains(window.canvas.mapFromScene(window.canvas.node_items["switch"].pos()))
    )


def test_enter_on_a_kind_in_the_list_places_it_too(window: MainWindow) -> None:
    item = window.device_list.item(6)  # the NAS
    viewport = window.device_list.viewport()
    pos = window.device_list.visualItemRect(item).center()
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
    QTest.keyClick(window.device_list, Qt.Key.Key_Return)
    assert [n.kind for n in window.document.project.nodes] == ["nas"]


# -------------------------------------------------------------------------- the files


def test_save_then_open_gives_the_same_homelab(
    window: MainWindow, tmp_path: Path, sample: Project
) -> None:
    window.document.replace(sample, None)
    target = tmp_path / ("lab" + SUFFIX)
    assert window.save_to(target)
    assert window.document.path == target
    assert not window.document.dirty
    assert window.windowTitle() == f"lab{SUFFIX} — HomeLabMaker"
    assert target.read_text(encoding="utf-8") == dumps(sample)

    window.document.replace(Project(), None)
    assert window.open_path(target)
    assert window.document.project == sample
    assert not window.document.dirty
    assert not window.document.can_undo


def test_saving_remembers_the_folder_in_the_preferences(window: MainWindow, tmp_path: Path) -> None:
    window.save_to(tmp_path / ("lab" + SUFFIX))
    assert settings.load().last_directory == str(tmp_path)


def test_save_as_adds_the_suffix_the_user_left_out(
    window: MainWindow, dialogs: Dialogs, tmp_path: Path
) -> None:
    window.canvas.add_device("nas", 1, 1)
    dialogs.save_as = str(tmp_path / "myhomelab")
    assert window.save()  # no path yet, so this is "Save as"
    assert (tmp_path / ("myhomelab" + SUFFIX)).is_file()
    assert window.document.path == tmp_path / ("myhomelab" + SUFFIX)


def test_cancelling_save_as_saves_nothing_and_keeps_the_changes(
    window: MainWindow, dialogs: Dialogs, tmp_path: Path
) -> None:
    window.canvas.add_device("nas", 1, 1)
    dialogs.save_as = ""
    assert not window.save()
    assert window.document.dirty
    assert list(tmp_path.glob("*" + SUFFIX)) == []


def test_save_writes_to_the_known_file_without_asking(
    window: MainWindow, dialogs: Dialogs, tmp_path: Path
) -> None:
    target = tmp_path / ("lab" + SUFFIX)
    window.canvas.add_device("nas", 1, 1)
    window.save_to(target)
    window.canvas.add_device("switch", 4, 1)
    dialogs.save_as = str(tmp_path / "must-not-be-used")
    assert window.save()
    assert len(load(target).nodes) == 2
    assert not (tmp_path / "must-not-be-used.homelab.json").exists()


def test_a_disk_that_refuses_is_reported_and_the_changes_stay(
    window: MainWindow, dialogs: Dialogs, tmp_path: Path
) -> None:
    window.canvas.add_device("nas", 1, 1)
    assert not window.save_to(tmp_path / "no-such-folder" / ("lab" + SUFFIX))
    assert len(dialogs.errors) == 1
    assert dialogs.errors[0].startswith("Cannot save the project")
    assert window.document.dirty


def test_a_broken_file_is_reported_and_the_open_document_is_untouched(
    window: MainWindow, dialogs: Dialogs, tmp_path: Path
) -> None:
    window.canvas.add_device("nas", 1, 1)
    before = window.document.project
    broken = tmp_path / ("broken" + SUFFIX)
    broken.write_text('{"format_version": 1, "nodes": [{"id": "A B"}]}', encoding="utf-8")
    assert not window.open_path(broken)
    assert window.document.project == before
    assert dialogs.errors
    assert "nodes[0]" in dialogs.errors[0]


def test_open_asks_before_discarding_changes(
    window: MainWindow, dialogs: Dialogs, tmp_path: Path, sample: Project
) -> None:
    target = tmp_path / ("lab" + SUFFIX)
    target.write_text(dumps(sample), encoding="utf-8")
    window.canvas.add_device("nas", 1, 1)
    dialogs.open_as = str(target)

    dialogs.answer = QMessageBox.StandardButton.Cancel
    window.open_document()
    assert dialogs.questions == 1
    assert len(window.document.project.nodes) == 1  # still the unsaved one

    dialogs.answer = QMessageBox.StandardButton.Discard
    window.open_document()
    assert window.document.project == sample


def test_open_with_the_dialog_cancelled_does_nothing(window: MainWindow, dialogs: Dialogs) -> None:
    window.canvas.add_device("nas", 1, 1)
    dialogs.open_as = ""
    window.open_document()
    assert dialogs.questions == 0
    assert len(window.document.project.nodes) == 1


def test_open_does_not_ask_when_there_is_nothing_to_lose(
    window: MainWindow, dialogs: Dialogs, tmp_path: Path, sample: Project
) -> None:
    target = tmp_path / ("lab" + SUFFIX)
    target.write_text(dumps(sample), encoding="utf-8")
    dialogs.open_as = str(target)
    window.open_document()
    assert dialogs.questions == 0
    assert window.document.project == sample


def test_new_asks_and_the_answers_do_what_they_say(
    window: MainWindow, dialogs: Dialogs, tmp_path: Path
) -> None:
    window.canvas.add_device("nas", 1, 1)

    dialogs.answer = QMessageBox.StandardButton.Cancel
    window.new_document()
    assert len(window.document.project.nodes) == 1

    dialogs.answer = QMessageBox.StandardButton.Discard
    window.new_document()
    assert window.document.project == Project()
    assert window.document.path is None

    window.canvas.add_device("nas", 1, 1)
    dialogs.answer = QMessageBox.StandardButton.Save
    dialogs.save_as = str(tmp_path / "kept")
    window.new_document()
    assert window.document.project == Project()
    assert len(load(tmp_path / ("kept" + SUFFIX)).nodes) == 1


def test_closing_asks_first_and_can_be_cancelled(window: MainWindow, dialogs: Dialogs) -> None:
    window.canvas.add_device("nas", 1, 1)
    event = QCloseEvent()
    window.closeEvent(event)
    assert dialogs.questions == 1
    assert not event.isAccepted()


def test_closing_a_clean_window_asks_nothing_and_saves_its_geometry(
    window: MainWindow, dialogs: Dialogs
) -> None:
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert dialogs.questions == 0
    assert settings.load().geometry != ""


# ------------------------------------------------------------------- the preferences


def test_the_theme_choice_is_applied_and_remembered(window: MainWindow) -> None:
    window.set_scheme("dark")
    assert window.tokens is DARK
    assert window.canvas.tokens is DARK
    assert window.scheme_actions["dark"].isChecked()
    assert settings.load().scheme == "dark"

    window.set_scheme("light")
    assert window.tokens is LIGHT
    assert window.canvas.tokens is LIGHT


def test_a_new_window_starts_with_the_remembered_theme(
    window: MainWindow, qapp: QApplication
) -> None:
    window.set_scheme("dark")
    again = MainWindow()
    try:
        assert again.tokens is DARK
        assert again.scheme_actions["dark"].isChecked()
        assert not again.scheme_actions["light"].isChecked()
    finally:
        again.deleteLater()


def test_a_window_can_be_given_a_document_and_preferences(qapp: QApplication) -> None:
    doc = Document(Project(name="Mine"), None)
    win = MainWindow(doc, settings.Preferences(scheme="light"))
    try:
        assert win.document is doc
        assert win.tokens is LIGHT
    finally:
        win.deleteLater()


# ------------------------------------------------------------------------- the menus


def test_every_action_is_reachable_from_a_menu(window: MainWindow) -> None:
    menus = [menu_action.menu() for menu_action in window.menuBar().actions()]
    in_menus = {action for menu in menus if isinstance(menu, QMenu) for action in menu.actions()}
    for name in (
        "new_action",
        "open_action",
        "save_action",
        "save_as_action",
        "quit_action",
        "undo_action",
        "redo_action",
        "rename_action",
        "delete_action",
        "select_all_action",
        "zoom_in_action",
        "zoom_out_action",
        "zoom_reset_action",
        "zoom_fit_action",
        "about_action",
    ):
        assert getattr(window, name) in in_menus, name


def test_the_menu_actions_drive_the_canvas(window: MainWindow) -> None:
    window.canvas.add_device("nas", 1, 1)
    window.zoom_in_action.trigger()
    assert window.canvas.zoom > 1
    window.zoom_reset_action.trigger()
    assert window.canvas.zoom == 1
    window.delete_action.trigger()
    assert window.document.project.nodes == ()
    window.undo_action.trigger()
    window.select_all_action.trigger()
    assert window.canvas.selected_ids() == ["nas"]
    window.zoom_out_action.trigger()
    window.zoom_fit_action.trigger()


def test_about_names_the_version_and_the_promise(window: MainWindow, dialogs: Dialogs) -> None:
    window.about()
    assert __version__ in dialogs.about_text
    assert "sends nothing anywhere" in dialogs.about_text
