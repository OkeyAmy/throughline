"""Exact reverse closure by batched, level-by-level BFS.

Why not a variable-length ``MATCH``: HydraDB rejects one whose fixed id is on the
far side of the arrow ("variable-length MATCH requires a fixed source id"), and
its path procedures return a *sample* of paths at depth (measured: full recall to
maxLen 4, 0.685 at maxLen 5 even with pathCount=100000). Impact analysis that
silently drops callers is a wrong answer, so the set comes from BFS and the
paths come from ``evidence.py``.

One round trip per (level x edge type), with the whole frontier passed as an
UNWIND batch — HydraDB walks the adjacency, the client only carries ids.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

#: (frontier, edge_type) -> [(source_id, neighbour_id), ...]
Expander = Callable[[Sequence[int], str], Iterable[tuple[int, int]]]


@dataclass
class LevelProgress:
    """Emitted as each BFS level completes, so a caller can stream the walk."""

    depth: int
    discovered: list[int]
    total: int
    round_trips: int
    frontier_size: int


@dataclass
class ClosureResult:
    hops: dict[int, int]
    """node id -> hop distance from the nearest seed (seeds excluded)."""
    exact: bool
    """True when the walk exhausted the graph rather than hitting a cap."""
    depth_reached: int
    round_trips: int
    ms: float = 0.0
    truncated_by: str | None = None
    edges: list[tuple[int, int, str]] = field(default_factory=list)
    """(source, neighbour, edge_type) pairs actually traversed — the evidence trail."""


def closure(
    expand: Expander,
    seeds: Sequence[int],
    edge_types: Sequence[str],
    max_depth: int = 6,
    node_cap: int = 20000,
    max_workers: int = 1,
    on_level: Callable[[LevelProgress], None] | None = None,
) -> ClosureResult:
    """Walk the inverse edges from `seeds` until the graph is exhausted or a cap hits.

    `max_workers` > 1 runs a level's edge types concurrently — they are independent
    queries against one snapshot. Results are merged in `edge_types` order so the
    answer is identical to the serial walk.
    """
    started = time.perf_counter()
    seen: dict[int, int] = {}
    seed_set = set(seeds)
    frontier = list(dict.fromkeys(seeds))
    round_trips = 0
    depth = 0
    truncated_by: str | None = None
    trail: list[tuple[int, int, str]] = []

    while frontier and depth < max_depth:
        depth += 1
        next_frontier: list[int] = []

        if max_workers > 1 and len(edge_types) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [pool.submit(expand, frontier, t) for t in edge_types]
                results = [(edge_types[i], list(f.result())) for i, f in enumerate(futures)]
        else:
            results = [(t, list(expand(frontier, t))) for t in edge_types]

        for edge_type, pairs in results:
            round_trips += 1
            for source, neighbour in pairs:
                trail.append((source, neighbour, edge_type))
                if neighbour in seed_set or neighbour in seen:
                    continue
                seen[neighbour] = depth
                next_frontier.append(neighbour)
                if len(seen) >= node_cap:
                    truncated_by = "node_cap"
                    break
            if truncated_by:
                break
        if on_level:
            on_level(
                LevelProgress(
                    depth=depth,
                    discovered=list(next_frontier),
                    total=len(seen),
                    round_trips=round_trips,
                    frontier_size=len(frontier),
                )
            )
        if truncated_by:
            break
        frontier = next_frontier

    if truncated_by is None and frontier and depth >= max_depth:
        truncated_by = "max_depth"

    return ClosureResult(
        hops=seen,
        exact=truncated_by is None,
        # The deepest hop that actually yielded a node — not the number of levels
        # walked, which is always one more when the walk runs to exhaustion.
        depth_reached=max(seen.values(), default=0),
        round_trips=round_trips,
        ms=(time.perf_counter() - started) * 1000,
        truncated_by=truncated_by,
        edges=trail,
    )
