"""The main window: menus, the device list, the canvas, and opening and saving files."""

import base64
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from homelab_maker import __version__, settings
from homelab_maker.checks import Severity
from homelab_maker.document import Document
from homelab_maker.export import to_drawio, to_markdown
from homelab_maker.gui import qt_theme
from homelab_maker.gui.canvas import Canvas
from homelab_maker.gui.findings import FindingsPanel
from homelab_maker.gui.flows import FlowsPanel
from homelab_maker.gui.icons import app_icon
from homelab_maker.gui.inspector import Inspector
from homelab_maker.gui.palette import Palette
from homelab_maker.gui.theme import Scheme
from homelab_maker.model import Medium, Project
from homelab_maker.outage import describe, what_goes_down
from homelab_maker.storage import ProjectFileError, load, save
from homelab_maker.viewmodel import (
    APP_NAME,
    PROJECT_SUFFIX,
    project_path,
    status_text,
    trail_text,
    window_title,
)

_FILE_FILTER = f"HomeLabMaker project (*{PROJECT_SUFFIX});;All files (*)"
_SCHEMES: tuple[tuple[Scheme, str], ...] = (
    ("system", "Follow the system"),
    ("light", "Light"),
    ("dark", "Dark"),
)


class MainWindow(QMainWindow):
    def __init__(
        self,
        document: Document | None = None,
        preferences: settings.Preferences | None = None,
    ) -> None:
        super().__init__()
        self.document = document if document is not None else Document()
        self.preferences = preferences if preferences is not None else settings.load()
        self.tokens = qt_theme.tokens_for(self.preferences.scheme)
        self._apply_to_application()

        self.canvas = Canvas(self.document, self.tokens)
        self.device_list = Palette(self.tokens)
        self.setCentralWidget(self.canvas)
        dock = QDockWidget("Devices", self)
        dock.setObjectName("devices-dock")
        dock.setWidget(self.device_list)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        self.inspector = Inspector(self.document, self.canvas)
        details = QDockWidget("Details", self)
        details.setObjectName("details-dock")
        details.setWidget(self.inspector)
        details.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details)

        self.findings = FindingsPanel(self.document, self.tokens)
        self.findings.reveal = self.canvas.reveal
        self.checks_dock = checks = QDockWidget("Checks", self)
        checks.setObjectName("checks-dock")
        checks.setWidget(self.findings)
        checks.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, checks)
        self.findings.counted.connect(lambda _count: self._update_ui())

        self.flows_panel = FlowsPanel(self.document, self.canvas, self.tokens)
        self.flows_dock = flows = QDockWidget("Flows", self)
        flows.setObjectName("flows-dock")
        flows.setWidget(self.flows_panel)
        flows.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, flows)
        self.tabifyDockWidget(checks, flows)
        flows.raise_()

        self._counts = QLabel()
        self.statusBar().addPermanentWidget(self._counts)
        self.setWindowIcon(app_icon())
        self.resize(1200, 780)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        # The drawing gets the room: the lists beside it and below it stay compact.
        self.resizeDocks([dock, details], [200, 400], Qt.Orientation.Horizontal)
        self.resizeDocks([checks], [300], Qt.Orientation.Vertical)

        self.device_list.kind_chosen.connect(self.canvas.add_at_center)
        self.canvas.status_message.connect(lambda text: self.statusBar().showMessage(text, 5000))
        self.canvas.selection_changed.connect(self._update_ui)
        self.canvas.view_changed.connect(self._update_ui)
        self.canvas.tool_changed.connect(self._update_ui)
        self.document.subscribe(self._update_ui)

        if self.preferences.geometry:
            self.restoreGeometry(QByteArray.fromBase64(self.preferences.geometry.encode("ascii")))
        self._update_ui()

    # ------------------------------------------------------------------------ actions

    def _action(
        self, text: str, slot: object, shortcut: str | QKeySequence.StandardKey = ""
    ) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _build_actions(self) -> None:
        std = QKeySequence.StandardKey
        self.new_action = self._action("&New", self.new_document, std.New)
        self.open_action = self._action("&Open…", self.open_document, std.Open)
        self.save_action = self._action("&Save", self.save, std.Save)
        self.save_as_action = self._action("Save &as…", self.save_as, std.SaveAs)
        self.export_image_action = self._action("Export an &image (PNG or SVG)…", self.export_image)
        self.export_markdown_action = self._action(
            "Export the &documentation (Markdown)…", self.export_markdown
        )
        self.export_drawio_action = self._action("Export a &draw.io diagram…", self.export_drawio)
        self.quit_action = self._action("&Quit", self.close, "Ctrl+Q")
        self.undo_action = self._action("&Undo", self.undo, std.Undo)
        self.redo_action = self._action("&Redo", self.redo, std.Redo)
        # Delete, Rename and Select all are handled by the canvas as keys, so these entries
        # only show the key in the menu and do not register a second shortcut.
        self.rename_action = self._action("Re&name\tF2", self.canvas.rename_selected)
        self.delete_action = self._action("&Delete\tDel", self.canvas.delete_selected)
        self.select_all_action = self._action("Select &all\tCtrl+A", self.canvas.select_all)
        self.zoom_in_action = self._action("Zoom &in", lambda: self.canvas.zoom_by(1.25), "Ctrl+=")
        self.zoom_out_action = self._action("Zoom &out", lambda: self.canvas.zoom_by(0.8), "Ctrl+-")
        self.zoom_reset_action = self._action("&Actual size", self.canvas.zoom_reset, "Ctrl+0")
        self.zoom_fit_action = self._action("&Fit everything", self.canvas.zoom_fit, "Ctrl+1")
        self.about_action = self._action(f"&About {APP_NAME}", self.about)
        self.up_action = self._action("&Up", self.canvas.leave, "Alt+Up")
        self.open_inside_action = self._action("Open &inside", self._open_selected, "Alt+Down")
        self.take_out_action = self._action("&Take out of its host", self.canvas.take_out)
        self.cable_action = self._action("&Cable tool", self._toggle_cable_tool, "Ctrl+K")
        self.cable_action.setCheckable(True)
        self.add_flow_action = self._action("Add &flow…", self.flows_panel.ask_for_flow, "Ctrl+L")
        self.outage_action = self._action(
            "What goes &down if I switch off the selection…", self.show_outage, "Ctrl+Shift+D"
        )
        self.back_to_normal_action = self._action(
            "&Back to normal", self.clear_outage, "Ctrl+Shift+N"
        )

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addActions([self.new_action, self.open_action])
        file_menu.addSeparator()
        file_menu.addActions([self.save_action, self.save_as_action])
        file_menu.addSeparator()
        file_menu.addActions(
            [self.export_image_action, self.export_markdown_action, self.export_drawio_action]
        )
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        edit_menu = bar.addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action])
        edit_menu.addSeparator()
        edit_menu.addActions([self.rename_action, self.delete_action, self.select_all_action])
        edit_menu.addSeparator()
        edit_menu.addActions([self.cable_action, self.open_inside_action])
        edit_menu.addActions([self.take_out_action, self.up_action])

        view_menu = bar.addMenu("&View")
        view_menu.addActions(
            [
                self.zoom_in_action,
                self.zoom_out_action,
                self.zoom_reset_action,
                self.zoom_fit_action,
            ]
        )
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("&Theme")
        group = QActionGroup(self)
        self.scheme_actions: dict[str, QAction] = {}
        for scheme, label in _SCHEMES:
            action = QAction(label, self, checkable=True)
            action.setChecked(scheme == self.preferences.scheme)
            action.triggered.connect(lambda _checked=False, s=scheme: self.set_scheme(s))
            group.addAction(action)
            theme_menu.addAction(action)
            self.scheme_actions[scheme] = action

        analysis_menu = bar.addMenu("&Analysis")
        analysis_menu.addAction(self.add_flow_action)
        analysis_menu.addSeparator()
        analysis_menu.addActions([self.outage_action, self.back_to_normal_action])

        bar.addMenu("&Help").addAction(self.about_action)

    def _build_toolbar(self) -> None:
        bar = QToolBar("Navigation", self)
        bar.setObjectName("navigation")
        bar.setMovable(False)
        bar.addAction(self.up_action)
        self.trail_label = QLabel()
        self.trail_label.setObjectName("trail")
        self.trail_label.setContentsMargins(8, 0, 16, 0)
        bar.addWidget(self.trail_label)
        bar.addSeparator()
        bar.addAction(self.cable_action)
        self.medium_box = QComboBox()
        self.medium_box.setObjectName("medium")
        for medium in Medium:
            self.medium_box.addItem(medium.value, medium)
        self.medium_box.currentIndexChanged.connect(self._medium_chosen)
        bar.addWidget(self.medium_box)
        self.addToolBar(bar)

    def _medium_chosen(self) -> None:
        # Qt hands a string enum back as a plain string.
        self.canvas.cable_medium = Medium(self.medium_box.currentText())

    def _toggle_cable_tool(self) -> None:
        self.canvas.set_cable_tool(self.cable_action.isChecked())

    def _open_selected(self) -> None:
        ids = self.canvas.selected_ids()
        if len(ids) == 1:
            self.canvas.enter(ids[0])

    def show_outage(self) -> None:
        """Switch off the selected devices on the drawing and say what stops working."""
        ids = self.canvas.selected_ids()
        if not ids:
            self.statusBar().showMessage("Select the devices to switch off first.", 5000)
            return
        outage = what_goes_down(self.document.project, ids)
        self.canvas.set_offline(frozenset(outage.stopped))
        QMessageBox.information(
            self,
            "What goes down",
            describe(self.document.project, outage)
            + "\n\nThis is what the drawing says, not what the real network will do.",
        )
        self._update_ui()

    def clear_outage(self) -> None:
        self.canvas.set_offline(frozenset())
        self._update_ui()

    def _update_ui(self) -> None:
        doc = self.document
        self.setWindowTitle(window_title(doc.path, doc.dirty))
        self.undo_action.setEnabled(doc.can_undo)
        self.redo_action.setEnabled(doc.can_redo)
        self.undo_action.setText(f"&Undo {doc.undo_label}" if doc.undo_label else "&Undo")
        self.redo_action.setText(f"&Redo {doc.redo_label}" if doc.redo_label else "&Redo")
        selected = self.canvas.selected_ids()
        self.delete_action.setEnabled(bool(selected) or self.canvas.selected_link is not None)
        self.up_action.setEnabled(self.canvas.view is not None)
        self.take_out_action.setEnabled(bool(selected) and self.canvas.view is not None)
        self.open_inside_action.setEnabled(
            len(selected) == 1 and self.canvas.can_enter(selected[0])
        )
        self.cable_action.setChecked(self.canvas.cable_tool)
        self.outage_action.setEnabled(bool(selected))
        self.back_to_normal_action.setEnabled(bool(self.canvas.offline))
        self.trail_label.setText(trail_text(doc.project, self.canvas.view))
        self.rename_action.setEnabled(len(selected) == 1)
        warnings = sum(1 for f in self.findings.findings if f.severity is Severity.WARNING)
        self._counts.setText(status_text(doc.project, len(selected), warnings))

    # ---------------------------------------------------------------------- the theme

    def _apply_to_application(self) -> None:
        app = QApplication.instance()
        if isinstance(app, QApplication):
            qt_theme.apply(app, self.tokens)

    def set_scheme(self, scheme: Scheme) -> None:
        self.preferences.scheme = scheme
        self.tokens = qt_theme.tokens_for(scheme)
        self._apply_to_application()
        self.canvas.set_tokens(self.tokens)
        self.device_list.set_tokens(self.tokens)
        self.findings.set_tokens(self.tokens)
        self.flows_panel.set_tokens(self.tokens)
        self.scheme_actions[scheme].setChecked(True)
        settings.save(self.preferences)

    # ------------------------------------------------------------------------- editing

    def undo(self) -> None:
        self.document.undo()

    def redo(self) -> None:
        self.document.redo()

    # --------------------------------------------------------------------------- files

    def _confirm_discard(self) -> bool:
        """Whether it is fine to throw away the unsaved changes (or save them first)."""
        if not self.document.dirty:
            return True
        name = self.document.path.name if self.document.path else "Untitled"
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"Save the changes to {name}?",
            buttons.Save | buttons.Discard | buttons.Cancel,
            buttons.Save,
        )
        if answer == buttons.Save:
            return self.save()
        return answer == buttons.Discard

    def new_document(self) -> None:
        if self._confirm_discard():
            self.document.replace(Project(), None)
            self.canvas.zoom_reset()

    def open_document(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Open project", self.preferences.last_directory, _FILE_FILTER
        )
        if chosen and self._confirm_discard():
            self.open_path(Path(chosen))

    def open_path(self, path: Path) -> bool:
        """Open a project file. Says why, and changes nothing, if it cannot be used."""
        try:
            project = load(path)
        except ProjectFileError as exc:
            QMessageBox.critical(self, "Cannot open the project", str(exc))
            return False
        self.document.replace(project, path)
        self._remember_directory(path)
        self.canvas.zoom_fit()
        return True

    def save(self) -> bool:
        if self.document.path is None:
            return self.save_as()
        return self.save_to(self.document.path)

    def save_as(self) -> bool:
        start = self.document.path.name if self.document.path else "homelab" + PROJECT_SUFFIX
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "Save project",
            str(Path(self.preferences.last_directory) / start),
            _FILE_FILTER,
        )
        if not chosen:
            return False
        return self.save_to(project_path(Path(chosen)))

    def save_to(self, path: Path) -> bool:
        try:
            save(path, self.document.project)
        except OSError as exc:
            QMessageBox.critical(
                self, "Cannot save the project", f"{path.name}: {exc.strerror or exc}"
            )
            return False
        self.document.mark_saved(path)
        self._remember_directory(path)
        self.statusBar().showMessage(f"Saved {path.name}", 5000)
        return True

    # ------------------------------------------------------------------------ exports

    def _export_target(self, title: str, suffix: str, filter_text: str) -> Path | None:
        name = self.document.path.name if self.document.path else "homelab"
        start = str(
            Path(self.preferences.last_directory) / (name.removesuffix(PROJECT_SUFFIX) + suffix)
        )
        chosen, _ = QFileDialog.getSaveFileName(self, title, start, filter_text)
        if not chosen:
            return None
        path = Path(chosen)
        return path if path.suffix else path.with_suffix(suffix)

    def _write_text(self, path: Path, text: str) -> bool:
        try:
            path.write_text(text, encoding="utf-8", newline="\n")
        except OSError as exc:
            QMessageBox.critical(self, "Cannot export", f"{path.name}: {exc.strerror or exc}")
            return False
        self.statusBar().showMessage(f"Exported {path.name}", 5000)
        return True

    def export_markdown(self) -> bool:
        path = self._export_target("Export the documentation", ".md", "Markdown (*.md)")
        return path is not None and self._write_text(path, to_markdown(self.document.project))

    def export_drawio(self) -> bool:
        path = self._export_target("Export a draw.io diagram", ".drawio", "draw.io (*.drawio)")
        return path is not None and self._write_text(path, to_drawio(self.document.project))

    def export_image(self) -> bool:
        path = self._export_target(
            "Export an image", ".png", "PNG image (*.png);;SVG image (*.svg)"
        )
        if path is None:
            return False
        try:
            self.canvas.save_image(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Cannot export", f"{path.name}: {exc}")
            return False
        self.statusBar().showMessage(f"Exported {path.name}", 5000)
        return True

    def _remember_directory(self, path: Path) -> None:
        self.preferences.last_directory = str(path.parent)
        settings.save(self.preferences)

    # ---------------------------------------------------------------------- the window

    def about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br>Draw your homelab on a grid and ask what can "
            "reach what.<br><br>It makes no network connection and sends nothing anywhere. "
            "MIT licence.",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_discard():
            event.ignore()
            return
        self.preferences.geometry = base64.b64encode(bytes(self.saveGeometry().data())).decode(
            "ascii"
        )
        settings.save(self.preferences)
        event.accept()
