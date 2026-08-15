"""Id registry.

HydraDB vertex ids are non-negative integers that the application assigns, and
relationship ids have to be supplied explicitly on every edge upsert
(``MERGE (s)-[r:T {id: row.rid}]->(d)``). graphify identifies nodes by string
slugs, so this maps ``(repo, slug) -> int`` and hands out edge ids from a
separate range.

``repo=None`` means the symbol is *external* — a package or module referenced by
a repo but not defined in it. Those share one global namespace, which is exactly
what makes a cross-repo edge possible: ``fastapi`` importing ``starlette_responses``
and ``starlette`` defining it resolve to the same node.
"""

from __future__ import annotations

import json
from pathlib import Path

EDGE_ID_BASE = 1_000_000_000


class Registry:
    def __init__(self) -> None:
        self._ids: dict[str, int] = {}
        self._reverse: dict[int, tuple[str | None, str]] = {}
        self._next_node = 0
        self._next_edge = EDGE_ID_BASE

    @staticmethod
    def _key(repo: str | None, slug: str) -> str:
        return f"{repo or ''}\x00{slug}"

    def node_id(self, repo: str | None, slug: str) -> int:
        key = self._key(repo, slug)
        if key not in self._ids:
            self._ids[key] = self._next_node
            self._reverse[self._next_node] = (repo, slug)
            self._next_node += 1
        return self._ids[key]

    def edge_id(self) -> int:
        eid = self._next_edge
        self._next_edge += 1
        return eid

    def lookup(self, node_id: int) -> tuple[str | None, str] | None:
        return self._reverse.get(node_id)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps({"ids": self._ids, "next_node": self._next_node, "next_edge": self._next_edge})
        )

    @classmethod
    def load(cls, path: str | Path) -> "Registry":
        data = json.loads(Path(path).read_text())
        reg = cls()
        reg._ids = data["ids"]
        reg._next_node = data["next_node"]
        reg._next_edge = data["next_edge"]
        for key, nid in reg._ids.items():
            repo, slug = key.split("\x00", 1)
            reg._reverse[nid] = (repo or None, slug)
        return reg
