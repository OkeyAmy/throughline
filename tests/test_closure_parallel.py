"""Edge types within a level are independent queries, so they can run at once.
Concurrency must not change the answer — only the wall clock."""

import threading
import time

from server.closure import closure

REVERSE = {
    "CALLED_BY": {3: [2], 2: [1]},
    "TESTED_BY": {3: [9]},
    "USED_BY": {3: [7], 7: [8]},
}


def expander(graph, delay=0.0):
    def expand(frontier, edge_type):
        if delay:
            time.sleep(delay)
        return [
            (node, neighbour)
            for node in frontier
            for neighbour in graph.get(edge_type, {}).get(node, [])
        ]

    return expand


TYPES = ["CALLED_BY", "TESTED_BY", "USED_BY"]


def test_parallel_walk_returns_the_same_hops_as_the_serial_one():
    serial = closure(expander(REVERSE), seeds=[3], edge_types=TYPES, max_depth=5)
    parallel = closure(expander(REVERSE), seeds=[3], edge_types=TYPES, max_depth=5, max_workers=4)
    assert parallel.hops == serial.hops == {2: 1, 9: 1, 7: 1, 1: 2, 8: 2}


def test_parallel_walk_reports_the_same_completeness_and_round_trips():
    serial = closure(expander(REVERSE), seeds=[3], edge_types=TYPES, max_depth=5)
    parallel = closure(expander(REVERSE), seeds=[3], edge_types=TYPES, max_depth=5, max_workers=4)
    assert (parallel.exact, parallel.round_trips) == (serial.exact, serial.round_trips)


def test_edge_types_within_a_level_actually_run_concurrently():
    """Without concurrency this walk costs 3 sequential delays per level."""
    seen_threads = set()

    def expand(frontier, edge_type):
        seen_threads.add(threading.get_ident())
        time.sleep(0.05)
        return [
            (node, neighbour)
            for node in frontier
            for neighbour in REVERSE.get(edge_type, {}).get(node, [])
        ]

    closure(expand, seeds=[3], edge_types=TYPES, max_depth=1, max_workers=3)
    # blindfold: invariant — three edge types dispatched at once means more than one
    # worker thread touched the expander.
    assert len(seen_threads) > 1


def test_the_node_cap_still_holds_under_concurrency():
    result = closure(
        expander(REVERSE), seeds=[3], edge_types=TYPES, max_depth=5, node_cap=2, max_workers=4
    )
    assert (len(result.hops), result.exact, result.truncated_by) == (2, False, "node_cap")
