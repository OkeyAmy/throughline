"""Turn a closure result into the rows the UI and the agent see.

Ordering encodes what a reviewer actually wants to know: how close the blast is,
and whether it left the repo they are editing.
"""

from __future__ import annotations

from collections.abc import Mapping

TEST_MARKERS = ("test_", "_test.", "/tests/", "spec.")


def is_test_path(path: str, name: str) -> bool:
    haystack = f"{path.lower()}|{name.lower()}"
    return any(marker in haystack for marker in TEST_MARKERS)


DOC_SUFFIXES = (".md", ".rst", ".txt", ".mdx")


def rank_symbols(candidates: list[dict], query: str) -> list[dict]:
    """Order symbol-search hits so the thing the user meant is first.

    graphify mints an unresolved stub every time a repo references a symbol it
    cannot see, so a popular class matches its own definition once and its stubs
    many times. Definitions win, source beats docs, exact name beats prefix.
    """

    def key(symbol: dict) -> tuple:
        path = (symbol.get("path") or "").lower()
        return (
            not (symbol.get("repo") and path),  # real definitions first
            path.endswith(DOC_SUFFIXES),  # source before documentation
            (symbol.get("name") or "") != query,  # exact name before prefix match
            len(symbol.get("name") or ""),
            symbol.get("id", 0),
        )

    return sorted(candidates, key=key)


def rank_impact(
    hops: Mapping[int, int], info: Mapping[int, dict], seed_repo: str
) -> list[dict]:
    rows: list[dict] = []
    for node_id, hop in hops.items():
        meta = info.get(node_id)
        if meta is None:
            continue
        repo = meta.get("repo") or "external"
        if repo == "external":
            # The joint between two repos, not a place anything breaks.
            continue
        path = meta.get("path") or ""
        name = meta.get("name") or str(node_id)
        rows.append(
            {
                "id": node_id,
                "name": name,
                "repo": repo,
                "path": path,
                "line": meta.get("line", -1),
                "hop": hop,
                "cross_repo": repo != seed_repo,
                "is_test": is_test_path(path, name),
            }
        )

    rows.sort(key=lambda r: (r["hop"], not r["cross_repo"], r["repo"], r["path"], r["name"]))
    return rows
