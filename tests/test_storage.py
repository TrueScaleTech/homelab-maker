import copy
import json
from pathlib import Path
from typing import Any

import pytest

from homelab_maker import storage
from homelab_maker.model import Node, Project
from homelab_maker.storage import FORMAT_VERSION, ProjectFileError, dumps, load, loads, save


def as_data(project: Project) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(dumps(project))
    return data


def reject(data: object, *, containing: str) -> None:
    with pytest.raises(ProjectFileError) as caught:
        loads(json.dumps(data))
    assert containing in str(caught.value)


# --------------------------------------------------------------------------- writing


def test_a_project_survives_a_round_trip(sample: Project) -> None:
    assert loads(dumps(sample)) == sample


def test_the_same_homelab_always_gives_the_same_bytes(sample: Project) -> None:
    shuffled = Project(
        sample.name,
        tuple(reversed(sample.nodes)),
        tuple(reversed(sample.links)),
        tuple(reversed(sample.zones)),
        tuple(reversed(sample.flows)),
    )
    assert dumps(shuffled) == dumps(sample)


def test_the_text_is_sorted_indented_and_ends_with_one_newline(sample: Project) -> None:
    text = dumps(sample)
    assert text.endswith("}\n")
    assert "\r" not in text
    assert text.startswith('{\n  "flows"')
    keys = list(json.loads(text))
    assert keys == sorted(keys)


def test_non_ascii_names_are_written_as_they_are() -> None:
    project = Project(name="Laboratorio di Zoë")
    assert "Zoë" in dumps(project)
    assert loads(dumps(project)).name == "Laboratorio di Zoë"


def test_the_format_version_is_written(sample: Project) -> None:
    assert as_data(sample)["format_version"] == FORMAT_VERSION


# --------------------------------------------------------------------------- reading


def test_a_minimal_project_needs_only_its_version() -> None:
    project = loads('{"format_version": 1}')
    assert project == Project()


def test_optional_fields_take_their_defaults() -> None:
    project = loads(
        json.dumps({"format_version": 1, "nodes": [{"id": "a", "kind": "nas", "name": "A"}]})
    )
    assert project.nodes == (Node("a", "nas", "A"),)


@pytest.mark.parametrize(
    ("text", "containing"),
    [
        ("", "not valid JSON"),
        ("{not json", "not valid JSON"),
        ("[]", "expected an object"),
        ('"hello"', "expected an object"),
        ("{}", "no valid format_version"),
        ('{"format_version": true}', "no valid format_version"),
        ('{"format_version": "1"}', "no valid format_version"),
        ('{"format_version": 0}', "no valid format_version"),
        ('{"format_version": NaN}', "NaN"),
        ('{"format_version": 1, "name": Infinity}', "Infinity"),
        ("[" * 100_000, "nested too deeply"),
    ],
)
def test_text_that_is_not_a_project_is_refused(text: str, containing: str) -> None:
    with pytest.raises(ProjectFileError, match=containing):
        loads(text)


def test_a_project_from_a_newer_format_is_refused_with_advice() -> None:
    with pytest.raises(ProjectFileError, match="update the application"):
        loads(json.dumps({"format_version": FORMAT_VERSION + 1, "shiny": "new"}))


def test_an_unknown_field_is_refused_and_named(sample: Project) -> None:
    data = as_data(sample)
    data["nodes"][0]["colour"] = "red"
    reject(data, containing="nodes[0]: unknown field 'colour'")


def test_an_unknown_top_level_field_is_refused(sample: Project) -> None:
    data = as_data(sample)
    data["theme"] = "dark"
    reject(data, containing="unknown field 'theme'")


def test_a_missing_required_field_is_named(sample: Project) -> None:
    data = as_data(sample)
    del data["nodes"][2]["kind"]
    reject(data, containing="nodes[2]: missing the field 'kind'")


@pytest.mark.parametrize(
    ("edit", "containing"),
    [
        (lambda d: d["nodes"][0].update(name=5), "nodes[0].name: expected text"),
        (lambda d: d["nodes"][0].update(x="3"), "nodes[0].x: expected a whole number"),
        (lambda d: d["nodes"][0].update(x=True), "nodes[0].x: expected a whole number"),
        (lambda d: d["nodes"][0].update(routes="yes"), "nodes[0].routes: expected true"),
        (lambda d: d["nodes"][0].update(parent=5), "nodes[0].parent: expected text or null"),
        (
            lambda d: d["nodes"][0]["interfaces"][0].update(vlan="10"),
            "vlan: expected a whole number or null",
        ),
        (lambda d: d["nodes"][0].update(interfaces={}), "nodes[0].interfaces: expected a list"),
        (lambda d: d.update(nodes=[1]), "nodes[0]: expected an object"),
        (
            lambda d: d["nodes"][0]["interfaces"][0].update(addresses=[7]),
            "nodes[0].interfaces[0].addresses: expected a list of text",
        ),
        (
            lambda d: d["nodes"][0]["interfaces"][0].update(trunk_vlans=[True]),
            "trunk_vlans: expected a list of whole numbers",
        ),
    ],
)
def test_a_value_of_the_wrong_type_is_refused_where_it_sits(
    sample: Project, edit: Any, containing: str
) -> None:
    data = as_data(sample)
    edit(data)
    reject(data, containing=containing)


@pytest.mark.parametrize(
    ("edit", "containing"),
    [
        (
            lambda d: d["nodes"][0]["interfaces"][0].update(vlan=5000),
            "nodes[0].interfaces[0]: VLAN must be between 1 and 4094",
        ),
        (
            lambda d: d["nodes"][0]["interfaces"][0].update(addresses=["nas.home"]),
            "nodes[0].interfaces[0]: 'nas.home' is not an IPv4 or IPv6 address",
        ),
        (
            lambda d: d["nodes"][0]["interfaces"][0].update(mode="hybrid"),
            "nodes[0].interfaces[0]",
        ),
        (lambda d: d["nodes"][0].update(id="Not An Id"), "nodes[0]: node id"),
        (lambda d: d["links"][0].update(medium="pigeon"), "links[0]"),
        (lambda d: d["links"][0]["a"].update(node="Bad Id"), "links[0].a"),
        (lambda d: d["flows"][0].update(port=0), "flows[0]: port must be between"),
        (lambda d: d["zones"][0].update(width=0), "zones[0]: width must be between"),
        (
            lambda d: d["nodes"][4]["rules"][0].update(source="10.0.0.0/33"),
            "rules[0]",
        ),
    ],
)
def test_a_value_that_the_model_refuses_is_reported_where_it_sits(
    sample: Project, edit: Any, containing: str
) -> None:
    data = as_data(sample)
    edit(data)
    reject(data, containing=containing)


def test_a_reference_to_something_missing_is_refused(sample: Project) -> None:
    data = as_data(sample)
    data["links"][0]["a"]["node"] = "ghost"
    reject(data, containing="the project is inconsistent")


def test_many_problems_are_summarised() -> None:
    nodes = [{"id": f"n{n}", "kind": "toaster", "name": f"T{n}", "x": n} for n in range(6)]
    with pytest.raises(ProjectFileError, match=r"and 3 more"):
        loads(json.dumps({"format_version": 1, "nodes": nodes}))


def test_loading_does_not_change_what_it_was_given(sample: Project) -> None:
    data = as_data(sample)
    before = copy.deepcopy(data)
    loads(json.dumps(data))
    assert data == before


# ------------------------------------------------------------------------------ files


def test_save_then_load_gives_the_same_project(tmp_path: Path, sample: Project) -> None:
    target = tmp_path / "lab.homelab.json"
    save(target, sample)
    assert load(target) == sample
    assert target.read_text(encoding="utf-8") == dumps(sample)


def test_save_writes_unix_line_endings_even_on_windows(tmp_path: Path, sample: Project) -> None:
    target = tmp_path / "lab.homelab.json"
    save(target, sample)
    assert b"\r" not in target.read_bytes()


def test_save_leaves_no_temporary_file_behind(tmp_path: Path, sample: Project) -> None:
    save(tmp_path / "lab.homelab.json", sample)
    assert [p.name for p in tmp_path.iterdir()] == ["lab.homelab.json"]


def test_a_failed_save_keeps_the_old_file_and_cleans_up(
    tmp_path: Path, sample: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "lab.homelab.json"
    target.write_text("old contents", encoding="utf-8")

    def refuse(self: Path, target: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        save(target, sample)
    assert target.read_text(encoding="utf-8") == "old contents"
    assert [p.name for p in tmp_path.iterdir()] == ["lab.homelab.json"]


def test_a_missing_file_is_reported_by_name(tmp_path: Path) -> None:
    with pytest.raises(ProjectFileError, match=r"nothing\.homelab\.json: cannot be read"):
        load(tmp_path / "nothing.homelab.json")


def test_a_file_over_the_limit_is_refused_before_it_is_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(storage, "MAX_FILE_BYTES", 100)
    big = tmp_path / "big.homelab.json"
    big.write_text(" " * 101 + '{"format_version": 1}', encoding="utf-8")
    with pytest.raises(ProjectFileError, match="larger than the"):
        load(big)


def test_a_file_that_is_not_text_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "binary.homelab.json"
    binary.write_bytes(b"\xff\xfe\x00\x01")
    with pytest.raises(ProjectFileError, match="not a UTF-8 text file"):
        load(binary)


def test_a_file_saved_by_notepad_with_a_byte_order_mark_still_loads(tmp_path: Path) -> None:
    target = tmp_path / "bom.homelab.json"
    target.write_bytes(b"\xef\xbb\xbf" + b'{"format_version": 1, "name": "Lab"}')
    assert load(target).name == "Lab"


def test_an_error_from_a_file_names_the_file(tmp_path: Path) -> None:
    target = tmp_path / "broken.homelab.json"
    target.write_text("{oops", encoding="utf-8")
    with pytest.raises(ProjectFileError, match=r"^broken\.homelab\.json: not valid JSON"):
        load(target)
