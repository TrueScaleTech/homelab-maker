from dataclasses import replace
from pathlib import Path

from homelab_maker.document import HISTORY_LIMIT, Document
from homelab_maker.model import Node, Project
from homelab_maker.operations import add_node


def modified(doc: Document) -> bool:
    # A function call, so the type checker does not remember an earlier assert about the property.
    return doc.dirty


def with_node(project: Project, name: str, x: int) -> Project:
    return replace(project, nodes=(*project.nodes, Node(name, "nas", name.upper(), x=x)))


def test_a_blank_document_is_clean_and_has_nothing_to_undo() -> None:
    doc = Document()
    assert not doc.dirty
    assert not doc.can_undo
    assert not doc.can_redo
    assert doc.path is None


def test_a_change_is_one_undoable_step_and_marks_the_document_modified() -> None:
    doc = Document()
    doc.apply(with_node(doc.project, "a", 0), "Add a")
    assert doc.dirty
    assert doc.undo_label == "Add a"
    assert doc.undo() == "Add a"
    assert doc.project == Project()
    assert not doc.dirty  # back at the saved state, so no longer modified


def test_redo_replays_what_was_undone_and_a_new_change_forgets_it() -> None:
    doc = Document()
    doc.apply(with_node(doc.project, "a", 0), "Add a")
    doc.undo()
    assert doc.redo_label == "Add a"
    doc.apply(with_node(doc.project, "b", 1), "Add b")
    assert not doc.can_redo
    assert doc.redo() is None


def test_undo_and_redo_on_an_empty_history_do_nothing() -> None:
    doc = Document()
    assert doc.undo() is None
    assert doc.redo() is None


def test_an_edit_that_changes_nothing_is_not_a_step() -> None:
    doc = Document()
    doc.apply(Project(), "Nothing")
    assert not doc.can_undo
    assert not doc.dirty


def test_the_history_is_bounded() -> None:
    doc = Document()
    project = doc.project
    for number in range(HISTORY_LIMIT + 20):
        project = with_node(project, f"n{number}", number)
        doc.apply(project, f"step {number}")
    steps = 0
    while doc.undo():
        steps += 1
    assert steps == HISTORY_LIMIT


def test_saving_marks_the_document_clean_until_the_next_change(tmp_path: Path) -> None:
    doc = Document()
    doc.apply(with_node(doc.project, "a", 0), "Add a")
    doc.mark_saved(tmp_path / "lab.homelab.json")
    assert not modified(doc)
    assert doc.path == tmp_path / "lab.homelab.json"
    doc.apply(with_node(doc.project, "b", 1), "Add b")
    assert modified(doc)
    doc.undo()
    assert not modified(doc)
    doc.undo()
    assert modified(doc)  # now it differs from what is on disk the other way round


def test_a_document_opened_from_a_file_is_clean(tmp_path: Path) -> None:
    project = with_node(Project(), "a", 0)
    doc = Document(project, tmp_path / "lab.homelab.json")
    assert not doc.dirty


def test_a_project_built_in_memory_and_never_saved_is_modified() -> None:
    assert Document(with_node(Project(), "a", 0)).dirty


def test_replacing_the_document_forgets_the_history(tmp_path: Path) -> None:
    doc = Document()
    doc.apply(with_node(doc.project, "a", 0), "Add a")
    doc.replace(with_node(Project(), "z", 3), tmp_path / "other.homelab.json")
    assert not doc.can_undo
    assert not doc.can_redo
    assert not doc.dirty
    doc.replace(Project(), None)
    assert not doc.dirty


def test_listeners_hear_about_every_kind_of_change(tmp_path: Path) -> None:
    doc = Document()
    heard: list[str] = []
    doc.subscribe(lambda: heard.append("changed"))
    project, _ = add_node(doc.project, "nas", 0, 0)
    doc.apply(project, "Add")
    doc.undo()
    doc.redo()
    doc.mark_saved(tmp_path / "lab.homelab.json")
    doc.replace(Project(), None)
    assert len(heard) == 5
