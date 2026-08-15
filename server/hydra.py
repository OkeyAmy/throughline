"""HydraDB-backed pieces of the query layer: frontier expansion, node hydration,
symbol lookup and evidence paths.

Every query form here is one the server actually accepts. The rejected variants
and their error strings are in claude.md §3 — notably: the batched read form
requires the *second* projection to be the destination id, so properties cannot
be fetched in a batch and hydration is deliberately limited to the rows the UI
shows (~1.5 ms each, measured).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from loader.writer import MAX_BATCH_ROWS, HydraClient, chunked
from server.ranking import rank_symbols

NODE_LABEL = "Sym"

#: Edge types a change propagates along, walked in the inverse direction.
#: CONTAINED_IN climbs from a symbol to its module so that module-level importers
#: (including importers in other repos, via PROVIDED_BY) are reached.
IMPACT_INVERSE_EDGES = (
    "CALLED_BY",
    "USED_BY",
    "EXTENDED_BY",
    "IMPORTED_BY",
    "CONTAINED_IN",
    "PROVIDED_BY",
)


def _value(cell: dict) -> Any:
    return cell["value"]


def rows_to_dicts(result: dict) -> list[dict]:
    columns = result["columns"]
    return [{col: _value(cell) for col, cell in zip(columns, row)} for row in result["rows"]]


class HydraExpander:
    """One round trip per (frontier batch x edge type).

    The batched read form is narrow: node patterns carry no labels, the known id
    must be on the pattern source, the first projection must be the row's id
    field and the second must be the destination id.
    """

    def __init__(self, client: HydraClient) -> None:
        self.client = client
        self.round_trips = 0

    def __call__(self, frontier: Sequence[int], edge_type: str) -> list[tuple[int, int]]:
        query = (
            "UNWIND $rows AS row "
            f"MATCH (s {{id: row.id}})-[:{edge_type}]->(c) "
            "RETURN row.id AS source, c.id AS neighbour"
        )
        pairs: list[tuple[int, int]] = []
        for batch in chunked(frontier, MAX_BATCH_ROWS):
            rows = [{"id": int(node_id)} for node_id in batch]
            result = self.client.query(query, {"rows": rows})
            self.round_trips += 1
            pairs.extend((_value(row[0]), _value(row[1])) for row in result["rows"])
        return pairs


def hydrate(client: HydraClient, node_ids: Sequence[int]) -> dict[int, dict]:
    """Fetch display properties for the nodes the caller intends to show."""
    out: dict[int, dict] = {}
    for node_id in node_ids:
        rows = client.query(
            "MATCH (n {id: $id}) RETURN n.name AS name, n.repo AS repo, n.path AS path, n.line AS line",
            {"id": int(node_id)},
        )["rows"]
        if not rows:
            out[int(node_id)] = {"id": int(node_id), "name": str(node_id), "repo": "", "path": "", "line": -1}
            continue
        name, repo, path, line = (_value(cell) for cell in rows[0])
        out[int(node_id)] = {
            "id": int(node_id),
            "name": name,
            "repo": repo or "external",
            "path": path or "",
            "line": line if isinstance(line, int) else -1,
        }
    return out


def find_symbols(client: HydraClient, prefix: str, limit: int = 20) -> list[dict]:
    """Prefix search. `CONTAINS` is unsupported in WHERE; `STARTS WITH` is not."""
    # Over-fetch, then rank locally: the query language has no ORDER BY over the
    # properties that decide which match is the definition (see ranking.rank_symbols).
    result = client.query(
        "MATCH (n:Sym) WHERE n.name STARTS WITH $prefix "
        "RETURN n.id AS id, n.name AS name, n.repo AS repo, n.path AS path, n.line AS line "
        f"LIMIT {int(limit) * 10}",
        {"prefix": prefix},
    )
    return rank_symbols(rows_to_dicts(result), prefix)[:limit]


def paths_between(
    client: HydraClient,
    source_id: int,
    target_id: int,
    edge_types: Sequence[str] = IMPACT_INVERSE_EDGES,
    max_len: int = 8,
    path_count: int = 12,
    result_limit: int = 20000,
) -> tuple[list[dict], bool]:
    """Why *this* row is in the blast radius: paths from the changed symbol to it.

    Asking for paths out of the impacted row instead returns nothing useful — a
    test file is a leaf, nothing points away from it. The evidence a reviewer wants
    is the chain that connects the change to the thing it reaches.
    """
    types = ", ".join(f'"{t}"' for t in edge_types)
    result = client.query(
        f"CALL algo.SPpaths({{sourceNode: {int(source_id)}, targetNode: {int(target_id)}, "
        f"relTypes: [{types}], relDirection: \"outgoing\", maxLen: {int(max_len)}, "
        f"pathCount: {int(path_count)}, resultLimit: {int(result_limit)}}}) "
        "YIELD path RETURN path"
    )
    return _paths_from_rows(result["rows"]), len(result["rows"]) < path_count


def _paths_from_rows(rows: list) -> list[dict]:
    paths: list[dict] = []
    for row in rows:
        value = row[0]["value"]
        paths.append(
            {
                "nodes": [
                    {
                        "id": n["id"],
                        "name": n["properties"].get("name", {}).get("String", str(n["id"])),
                        "repo": n["properties"].get("repo", {}).get("String", ""),
                        "path": n["properties"].get("path", {}).get("String", ""),
                    }
                    for n in value["nodes"]
                ],
                "edges": [
                    {"type": e["edge_type"], "src": e["src"], "dst": e["dst"]}
                    for e in value["relationships"]
                ],
            }
        )
    return paths


def evidence_paths(
    client: HydraClient,
    source_id: int,
    edge_types: Sequence[str] = IMPACT_INVERSE_EDGES,
    max_len: int = 4,
    path_count: int = 200,
    result_limit: int = 20000,
) -> tuple[list[dict], bool]:
    """Top-K evidence paths from a native path procedure.

    Returns (paths, complete). `complete` is False when the server returned as
    many paths as were asked for, which is the only honest signal that more exist
    — measured behaviour: full recall to maxLen 4, 0.685 at maxLen 5 even with
    pathCount 100000. The set answer never comes from here (see closure.py).
    """
    types = ", ".join(f'"{t}"' for t in edge_types)
    result = client.query(
        f"CALL algo.SSpaths({{sourceNode: {int(source_id)}, relTypes: [{types}], "
        f"relDirection: \"outgoing\", maxLen: {int(max_len)}, pathCount: {int(path_count)}, "
        f"resultLimit: {int(result_limit)}}}) YIELD path RETURN path"
    )
    return _paths_from_rows(result["rows"]), len(result["rows"]) < path_count
