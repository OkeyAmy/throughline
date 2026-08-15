"""throughline MCP server — the same traversal, in the agent's hands.

Structured after `hydra-db/hydradb-mcp`: MCPServer, stdio by default, tools that
are thin wrappers over the query layer so there is one source of truth for how
the graph is walked.

    python -m mcp_server                 # stdio, for Claude Code / Codex / Cursor
"""

from __future__ import annotations

import os
import re

from mcp.server.mcpserver import MCPServer

from loader.writer import HydraClient
from server.closure import closure
from server.hydra import (
    IMPACT_INVERSE_EDGES,
    HydraExpander,
    evidence_paths,
    find_symbols,
    hydrate,
    paths_between,
)
from server.ranking import rank_impact

HYDRA_URL = os.environ.get("HYDRADB_URL", "http://127.0.0.1:8443")
HYDRA_TOKEN = os.environ.get("HYDRADB_TOKEN", "local-development-token-32-bytes")
WORKERS = int(os.environ.get("THROUGHLINE_WORKERS", "6"))

mcp = MCPServer(
    "throughline",
    instructions=(
        "Cross-repo change impact from a code graph in HydraDB. Ask impact_of_change "
        "before editing a shared symbol, and tests_for before pushing."
    ),
    version="0.1.0",
)


def _client() -> HydraClient:
    return HydraClient(base_url=HYDRA_URL, token=HYDRA_TOKEN)


def _resolve(client: HydraClient, symbol: str) -> dict | None:
    matches = [s for s in find_symbols(client, symbol, limit=25) if s.get("repo")]
    return matches[0] if matches else None


@mcp.tool()
def find_symbol(name: str, limit: int = 10) -> dict:
    """Find symbols by name prefix across every repo in the workspace.

    Returns definitions first (a symbol referenced from another repo also exists
    as an unresolved stub, which is a valid id but not the thing you edit).
    """
    client = _client()
    try:
        return {"symbols": find_symbols(client, name, limit=limit)}
    finally:
        client.close()


@mcp.tool()
def impact_of_change(symbol: str, max_depth: int = 12, limit: int = 60) -> dict:
    """What breaks if `symbol` changes — across every repo in the workspace.

    Walks HydraDB's inverse edges (callers, users, subclasses, importers, and the
    cross-repo PROVIDES joint) level by level. The `trust` block says whether the
    answer is a complete closure or was cut short by a cap — treat a non-exact
    answer as a lower bound, never as the full set.
    """
    client = _client()
    try:
        seed = _resolve(client, symbol)
        if seed is None:
            return {"error": f"no symbol matching {symbol!r}"}

        result = closure(
            HydraExpander(client),
            seeds=[seed["id"]],
            edge_types=list(IMPACT_INVERSE_EDGES),
            max_depth=max_depth,
            max_workers=WORKERS,
        )
        shown = sorted(result.hops.items(), key=lambda kv: kv[1])[: limit * 3]
        info = hydrate(client, [nid for nid, _ in shown])
        rows = rank_impact(dict(shown), info, seed_repo=seed.get("repo", ""))[:limit]
        return {
            "seed": seed,
            "impacted_total": len(result.hops),
            "rows": rows,
            "cross_repo": [r for r in rows if r["cross_repo"]][:20],
            "trust": {
                "exact": result.exact,
                "truncated_by": result.truncated_by,
                "depth": result.depth_reached,
                "round_trips": result.round_trips,
            },
        }
    finally:
        client.close()


@mcp.tool()
def tests_for(symbol: str, max_depth: int = 6, limit: int = 40) -> dict:
    """The tests that reach `symbol` — what to run before you push this change."""
    client = _client()
    try:
        seed = _resolve(client, symbol)
        if seed is None:
            return {"error": f"no symbol matching {symbol!r}"}
        result = closure(
            HydraExpander(client),
            seeds=[seed["id"]],
            edge_types=list(IMPACT_INVERSE_EDGES),
            max_depth=max_depth,
            max_workers=WORKERS,
        )
        info = hydrate(client, list(result.hops)[:1500])
        rows = rank_impact(result.hops, info, seed_repo=seed.get("repo", ""))
        tests = [r for r in rows if r["is_test"]][:limit]
        return {
            "seed": seed,
            "tests": tests,
            "files": sorted({t["path"] for t in tests}),
            "trust": {"exact": result.exact, "depth": result.depth_reached},
        }
    finally:
        client.close()


@mcp.tool()
def callers_of(symbol: str, depth: int = 2, limit: int = 40) -> dict:
    """Who calls `symbol`, within `depth` hops — the narrow question.

    Only call and use edges are walked, so this is the direct answer to "who uses
    this", without the module-level importers that `impact_of_change` includes.
    """
    client = _client()
    try:
        seed = _resolve(client, symbol)
        if seed is None:
            return {"error": f"no symbol matching {symbol!r}"}
        result = closure(
            HydraExpander(client),
            seeds=[seed["id"]],
            edge_types=["CALLED_BY", "USED_BY", "EXTENDED_BY"],
            max_depth=depth,
            max_workers=WORKERS,
        )
        info = hydrate(client, list(result.hops)[: limit * 3])
        rows = rank_impact(result.hops, info, seed_repo=seed.get("repo", ""))[:limit]
        return {
            "seed": seed,
            "callers": rows,
            "trust": {"exact": result.exact, "depth": result.depth_reached},
        }
    finally:
        client.close()


@mcp.tool()
def code_context(question: str, limit: int = 25) -> dict:
    """Graph-grounded context for a plain-English question about the codebase.

    Resolves the question to a symbol, walks the impact closure, and returns the
    symbol, the reached code with hop distances, and the paths that connect them —
    the context an agent needs before editing shared code, assembled by traversal
    rather than by similarity.
    """
    client = _client()
    try:
        candidates = find_symbols(client, _first_identifier(question), limit=20)
        ranked = [c for c in candidates if c.get("repo")] or candidates
        if not ranked:
            return {"error": f"nothing in the graph matches {question!r}"}
        seed = ranked[0]
        result = closure(
            HydraExpander(client),
            seeds=[seed["id"]],
            edge_types=list(IMPACT_INVERSE_EDGES),
            max_depth=12,  # deep enough to exhaust rather than cap
            max_workers=WORKERS,
        )
        shown = sorted(result.hops.items(), key=lambda kv: kv[1])[: limit * 3]
        info = hydrate(client, [nid for nid, _ in shown])
        rows = rank_impact(dict(shown), info, seed_repo=seed.get("repo", ""))[:limit]
        paths, complete = paths_between(client, seed["id"], rows[0]["id"]) if rows else ([], True)
        return {
            "question": question,
            "resolved_to": seed,
            "context": rows,
            "example_paths": paths[:3],
            "trust": {
                "exact_closure": result.exact,
                "paths_complete": complete,
                "impacted_total": len(result.hops),
                "retrieval": "graph traversal in HydraDB, no embeddings",
            },
        }
    finally:
        client.close()


def _first_identifier(question: str) -> str:
    """Longest word in the question that could name code — the search prefix."""
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", question or "")
    words = [w for w in words if len(w) > 2 and w.lower() not in _STOPWORDS]
    return max(words, key=len) if words else (question or "").strip()


_STOPWORDS = {
    "what", "who", "which", "where", "when", "how", "does", "the", "and", "for",
    "this", "that", "change", "changes", "breaks", "break", "calls", "uses",
    "tests", "test", "code", "function", "class", "module", "repo", "happens",
    "impact", "would", "should", "could", "about", "into",
}


@mcp.tool()
def why_connected(symbol: str, max_len: int = 4, path_count: int = 40) -> dict:
    """Evidence paths out of `symbol` — the actual hops, with edge types.

    These come from HydraDB's native path procedure and are a *sample* at depth:
    `trust.complete` is false when more paths exist than were returned. Use them
    to explain an answer, never to enumerate one.
    """
    client = _client()
    try:
        seed = _resolve(client, symbol)
        if seed is None:
            return {"error": f"no symbol matching {symbol!r}"}
        paths, complete = evidence_paths(
            client, seed["id"], max_len=max_len, path_count=path_count
        )
        return {"seed": seed, "paths": paths, "trust": {"complete": complete}}
    finally:
        client.close()


def main() -> None:
    mcp.run(transport=os.environ.get("THROUGHLINE_MCP_TRANSPORT", "stdio"))


if __name__ == "__main__":
    main()
