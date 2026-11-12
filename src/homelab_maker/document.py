"""The open document: the current project, its file, and the undo history.

A project is immutable, so the history is just the earlier projects. Whether the document
has unsaved changes is decided by comparing the current project with the one last saved,
which means undoing back to the saved state clears the "modified" mark.
"""

from collections.abc import Callable
from pathlib import Path

from homelab_maker.model import Project

HISTORY_LIMIT = 200


def _clean_baseline(project: Project, path: Path | None) -> Project | None:
    """The project that counts as "saved", or ``None`` if the document has no such state.

    A blank document is clean, and so is one just read from a file. A project built in
    memory that has never been written anywhere is not.
    """
    return project if path is not None or project == Project() else None


class Document:
    def __init__(self, project: Project | None = None, path: Path | None = None) -> None:
        self._project = project if project is not None else Project()
        self._saved = _clean_baseline(self._project, path)
        self._path = path
        self._undo: list[tuple[str, Project]] = []
        self._redo: list[tuple[str, Project]] = []
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------------- state

    @property
    def project(self) -> Project:
        return self._project

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def dirty(self) -> bool:
        return self._project != self._saved

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str | None:
        return self._undo[-1][0] if self._undo else None

    @property
    def redo_label(self) -> str | None:
        return self._redo[-1][0] if self._redo else None

    def subscribe(self, listener: Callable[[], None]) -> None:
        """Call ``listener`` after every change of the project, the path or the history."""
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    # ----------------------------------------------------------------------- changes

    def apply(self, project: Project, label: str) -> None:
        """Make ``project`` the current one as a single undoable step."""
        if project == self._project:
            return
        self._undo.append((label, self._project))
        del self._undo[:-HISTORY_LIMIT]
        self._redo.clear()
        self._project = project
        self._notify()

    def undo(self) -> str | None:
        """Go back one step. Returns the label of what was undone, or ``None``."""
        if not self._undo:
            return None
        label, before = self._undo.pop()
        self._redo.append((label, self._project))
        self._project = before
        self._notify()
        return label

    def redo(self) -> str | None:
        if not self._redo:
            return None
        label, after = self._redo.pop()
        self._undo.append((label, self._project))
        self._project = after
        self._notify()
        return label

    # ------------------------------------------------------------------------- files

    def replace(self, project: Project, path: Path | None) -> None:
        """Start over with another project (New or Open): the history is forgotten."""
        self._project = project
        self._path = path
        self._saved = _clean_baseline(project, path)
        self._undo.clear()
        self._redo.clear()
        self._notify()

    def mark_saved(self, path: Path) -> None:
        """Record that the current project is on disk at ``path``."""
        self._path = path
        self._saved = self._project
        self._notify()
