"""The UI streams the walk level by level — watching the frontier expand is the
proof that HydraDB is doing a hop at a time. That needs a progress callback."""

from server.closure import closure

REVERSE = {"CALLED_BY": {3: [2, 4], 2: [1]}}


def expand(frontier, edge_type):
    return [
        (node, neighbour)
        for node in frontier
        for neighbour in REVERSE.get(edge_type, {}).get(node, [])
    ]


def test_each_level_reports_its_depth_and_what_it_found():
    levels = []
    closure(expand, seeds=[3], edge_types=["CALLED_BY"], max_depth=5, on_level=levels.append)
    # The last level discovers nothing: {1} still has to be queried to prove it has
    # no callers, and reporting it is how the UI knows the walk finished.
    assert [(lvl.depth, sorted(lvl.discovered), lvl.total) for lvl in levels] == [
        (1, [2, 4], 2),
        (2, [1], 3),
        (3, [], 3),
    ]


def test_a_level_that_discovers_nothing_still_reports_so_the_ui_can_stop():
    levels = []
    closure(expand, seeds=[1], edge_types=["CALLED_BY"], max_depth=3, on_level=levels.append)
    assert [(lvl.depth, lvl.discovered) for lvl in levels] == [(1, [])]


def test_progress_reporting_does_not_change_the_result():
    with_cb = closure(expand, seeds=[3], edge_types=["CALLED_BY"], max_depth=5, on_level=lambda _: None)
    without = closure(expand, seeds=[3], edge_types=["CALLED_BY"], max_depth=5)
    assert (with_cb.hops, with_cb.exact) == (without.hops, without.exact)


def test_levels_carry_the_round_trip_count_so_far():
    levels = []
    closure(expand, seeds=[3], edge_types=["CALLED_BY"], max_depth=5, on_level=levels.append)
    # blindfold: math — one edge type, so one round trip per level walked, and three
    # levels get walked before the frontier empties.
    assert [lvl.round_trips for lvl in levels] == [1, 2, 3]
