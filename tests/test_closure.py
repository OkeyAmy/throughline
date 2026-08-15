"""The closure layer is the answer engine: everything the product claims about
impact is this function's output, so it is tested against hand-computed graphs."""

from server.closure import closure

# 1 -> 2 -> 3  (CALLS), plus a test node 9 covering 3, and a cycle 4 <-> 5.
REVERSE = {
    "CALLED_BY": {3: [2], 2: [1]},
    "TESTED_BY": {3: [9]},
}
CYCLE = {"CALLED_BY": {4: [5], 5: [4]}}


def expander(graph):
    """Fake expander with the same contract as the HydraDB one: given a frontier
    and an edge type, return (source, neighbour) pairs."""
    calls = []

    def expand(frontier, edge_type):
        calls.append((tuple(frontier), edge_type))
        pairs = []
        for node in frontier:
            for neighbour in graph.get(edge_type, {}).get(node, []):
                pairs.append((node, neighbour))
        return pairs

    expand.calls = calls
    return expand


def test_transitive_callers_are_returned_with_their_hop_distance():
    result = closure(expander(REVERSE), seeds=[3], edge_types=["CALLED_BY"], max_depth=5)
    assert result.hops == {2: 1, 1: 2}


def test_several_edge_types_are_unioned_in_one_walk():
    result = closure(
        expander(REVERSE), seeds=[3], edge_types=["CALLED_BY", "TESTED_BY"], max_depth=5
    )
    assert result.hops == {2: 1, 9: 1, 1: 2}


def test_a_walk_that_exhausts_the_graph_is_exact():
    result = closure(expander(REVERSE), seeds=[3], edge_types=["CALLED_BY"], max_depth=5)
    assert (result.exact, result.depth_reached) == (True, 2)


def test_hitting_the_depth_cap_is_reported_as_not_exact():
    """An impact answer that silently drops callers is a wrong answer, so the
    caller must be able to tell a complete closure from a truncated one."""
    result = closure(expander(REVERSE), seeds=[3], edge_types=["CALLED_BY"], max_depth=1)
    assert (result.exact, result.hops, result.truncated_by) == (False, {2: 1}, "max_depth")


def test_cycles_terminate_and_do_not_revisit():
    result = closure(expander(CYCLE), seeds=[4], edge_types=["CALLED_BY"], max_depth=10)
    assert (result.hops, result.exact) == ({5: 1}, True)


def test_seeds_are_not_reported_as_their_own_impact():
    result = closure(expander(REVERSE), seeds=[3], edge_types=["CALLED_BY"], max_depth=5)
    assert 3 not in result.hops


def test_the_node_cap_stops_the_walk_and_says_so():
    result = closure(
        expander(REVERSE), seeds=[3], edge_types=["CALLED_BY", "TESTED_BY"], max_depth=5, node_cap=1
    )
    assert (len(result.hops), result.exact, result.truncated_by) == (1, False, "node_cap")


def test_round_trips_are_counted_per_level_and_edge_type():
    """Latency is a judged criterion and every round trip is a network hop, so the
    count is part of the answer, not a debug detail."""
    expand = expander(REVERSE)
    result = closure(expand, seeds=[3], edge_types=["CALLED_BY", "TESTED_BY"], max_depth=5)
    # blindfold: math — 3 non-empty frontiers get queried ({3}, then {2,9}, then {1}),
    # 2 edge types each. {1} must be queried too: not querying it is how you'd miss
    # a caller. The 4th level has an empty frontier and costs nothing.
    assert result.round_trips == 6  # blindfold: math — 3 non-empty frontiers x 2 edge types
    assert len(expand.calls) == 6  # blindfold: math — same count, observed at the boundary


def test_an_empty_seed_set_does_no_work():
    expand = expander(REVERSE)
    result = closure(expand, seeds=[], edge_types=["CALLED_BY"], max_depth=5)
    assert (result.hops, result.round_trips, result.exact) == ({}, 0, True)
