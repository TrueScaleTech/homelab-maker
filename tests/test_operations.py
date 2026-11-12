import pytest

from homelab_maker.model import GRID_LIMIT, Node, Project, Rule, RuleAction
from homelab_maker.operations import (
    add_node,
    can_move,
    delete_nodes,
    display_name,
    move_nodes,
    nearest_free_cell,
    rename_node,
)
from homelab_maker.validation import validate

# ------------------------------------------------------------------------ placing


def test_the_first_device_goes_exactly_where_it_was_dropped() -> None:
    project, node_id = add_node(Project(), "nas", 4, 2)
    node = project.node(node_id)
    assert node is not None
    assert (node.x, node.y) == (4, 2)


def test_a_device_dropped_on_a_taken_cell_lands_on_the_nearest_free_one() -> None:
    project, _ = add_node(Project(), "nas", 0, 0)
    project, second = add_node(project, "switch", 0, 0)
    node = project.node(second)
    assert node is not None
    assert (node.x, node.y) != (0, 0)
    assert abs(node.x) + abs(node.y) == 1  # a direct neighbour
    assert validate(project) == []


def test_ten_drops_on_one_cell_make_ten_distinct_cells() -> None:
    project = Project()
    for _ in range(10):
        project, _ = add_node(project, "iot", 0, 0)
    assert len({(n.x, n.y) for n in project.nodes}) == 10
    assert validate(project) == []


def test_a_new_device_gets_its_kind_name_and_then_a_number() -> None:
    project, _ = add_node(Project(), "switch", 0, 0)
    project, _ = add_node(project, "switch", 3, 0)
    assert sorted(n.name for n in project.nodes) == ["Switch", "Switch 2"]
    assert sorted(n.id for n in project.nodes) == ["switch", "switch-2"]


def test_an_unknown_kind_cannot_be_placed() -> None:
    with pytest.raises(ValueError, match="unknown device kind"):
        add_node(Project(), "toaster", 0, 0)


def test_the_search_for_a_free_cell_is_predictable() -> None:
    project, _ = add_node(Project(), "nas", 0, 0)
    assert nearest_free_cell(project, 0, 0) == (0, -1)  # above wins over the others


def test_a_free_cell_is_found_at_the_edge_of_the_grid() -> None:
    project, _ = add_node(Project(), "nas", GRID_LIMIT, GRID_LIMIT)
    x, y = nearest_free_cell(project, GRID_LIMIT, GRID_LIMIT)
    assert abs(x) <= GRID_LIMIT
    assert abs(y) <= GRID_LIMIT
    assert (x, y) != (GRID_LIMIT, GRID_LIMIT)


def test_display_name_counts_up() -> None:
    project = Project(nodes=(Node("a", "nas", "NAS"), Node("b", "nas", "NAS 2", x=1)))
    assert display_name(project, "NAS") == "NAS 3"
    assert display_name(project, "Switch") == "Switch"


# ------------------------------------------------------------------------- moving


def two_and_one() -> Project:
    return Project(
        nodes=(
            Node("a", "nas", "A", x=0, y=0),
            Node("b", "nas", "B", x=1, y=0),
            Node("c", "nas", "C", x=5, y=5),
        )
    )


def test_a_group_moves_together_by_the_same_amount() -> None:
    moved = move_nodes(two_and_one(), {"a", "b"}, 3, 2)
    assert [(n.id, n.x, n.y) for n in moved.nodes] == [("a", 3, 2), ("b", 4, 2), ("c", 5, 5)]


def test_a_move_onto_a_taken_cell_is_refused() -> None:
    project = two_and_one()
    assert not can_move(project, {"a"}, 1, 0)
    with pytest.raises(ValueError, match="taken"):
        move_nodes(project, {"a"}, 1, 0)


def test_neighbours_can_swap_into_each_others_cells_as_a_group() -> None:
    # Moving a and b one cell right is fine: b leaves the cell a arrives at.
    assert can_move(two_and_one(), {"a", "b"}, 1, 0)


def test_a_move_off_the_grid_is_refused() -> None:
    assert not can_move(two_and_one(), {"a"}, GRID_LIMIT + 1, 0)


def test_moving_nothing_is_refused() -> None:
    assert not can_move(two_and_one(), set(), 1, 0)
    assert not can_move(two_and_one(), {"ghost"}, 1, 0)


def test_what_is_inside_a_host_keeps_its_place_inside_it() -> None:
    project = Project(
        nodes=(
            Node("nas", "nas", "NAS", x=2, y=2),
            Node("vm1", "vm", "VM", x=0, y=0, parent="nas"),
        )
    )
    moved = move_nodes(project, {"nas"}, 4, 0)
    vm = moved.node("vm1")
    assert vm is not None
    assert (vm.x, vm.y, vm.parent) == (0, 0, "nas")


def test_children_of_different_hosts_may_share_a_cell() -> None:
    project = Project(
        nodes=(
            Node("n1", "nas", "N1", x=0, y=0),
            Node("n2", "nas", "N2", x=3, y=0),
            Node("v1", "vm", "V1", x=0, y=0, parent="n1"),
            Node("v2", "vm", "V2", x=1, y=0, parent="n2"),
        )
    )
    assert can_move(project, {"v2"}, -1, 0)


# ------------------------------------------------------------------------ renaming


def test_a_node_is_renamed_and_the_old_project_is_untouched() -> None:
    before = two_and_one()
    after = rename_node(before, "a", "  Backup NAS  ")
    node = after.node("a")
    assert node is not None
    assert node.name == "Backup NAS"
    old = before.node("a")
    assert old is not None
    assert old.name == "A"


def test_an_empty_name_is_refused() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        rename_node(two_and_one(), "a", "   ")


def test_renaming_a_missing_node_is_refused() -> None:
    with pytest.raises(ValueError, match="no node"):
        rename_node(two_and_one(), "ghost", "X")


# ------------------------------------------------------------------------ deleting


def test_deleting_the_example_nas_removes_what_depended_on_it(sample: Project) -> None:
    after = delete_nodes(sample, {"nas"})
    assert validate(after) == []
    left = {node.id for node in after.nodes}
    # The NAS, its two virtual machines and the two containers inside them.
    assert not left & {"nas", "home-assistant", "docker-host", "nextcloud", "vaultwarden"}
    assert {"gateway", "switch", "laptop"} <= left
    # Its cable and the flows to and from it are gone; the unrelated ones stay.
    assert "switch-nas" not in {link.id for link in after.links}
    assert {flow.id for flow in after.flows} == set()


def test_rules_that_named_a_deleted_node_are_dropped_and_the_rest_kept(sample: Project) -> None:
    gateway = sample.node("gateway")
    assert gateway is not None
    assert any(rule.destination == "nas" for rule in gateway.rules)
    after = delete_nodes(sample, {"nas"})
    new_gateway = after.node("gateway")
    assert new_gateway is not None
    assert all("nas" not in (rule.source, rule.destination) for rule in new_gateway.rules)
    assert len(new_gateway.rules) == len(gateway.rules) - 1


def test_deleting_a_guest_leaves_its_host() -> None:
    project = Project(
        nodes=(Node("nas", "nas", "NAS"), Node("vm1", "vm", "VM", parent="nas")),
    )
    after = delete_nodes(project, {"vm1"})
    assert [n.id for n in after.nodes] == ["nas"]


def test_deleting_nothing_changes_nothing(sample: Project) -> None:
    assert delete_nodes(sample, set()) == sample
    assert delete_nodes(sample, {"ghost"}) == sample


def test_a_rule_without_references_is_not_rewritten() -> None:
    gateway = Node("gw", "firewall", "GW", rules=(Rule(RuleAction.ALLOW, "10.0.0.0/8"),))
    project = Project(nodes=(gateway, Node("pc", "workstation", "PC", x=1)))
    after = delete_nodes(project, {"pc"})
    assert after.node("gw") is gateway
