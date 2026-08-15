"""HydraDB HTTP client and batched writer.

Every constraint encoded here was measured against a running node, not read off
a doc page — see claude.md §3 for the error strings that produced each rule.
"""

from __future__ import annotations

import re
import time
from typing import Any, Iterable, Iterator, Sequence

import httpx

#: An UNWIND batch larger than this is rejected by admission control with
#: "client_query_batch_items rejected by admission control".
MAX_BATCH_ROWS = 1000

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def chunked(rows: Iterable[Any], size: int = MAX_BATCH_ROWS) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def _identifier(value: str, what: str) -> str:
    if not _IDENTIFIER.match(value):
        raise ValueError(f"{what} must be a bare identifier, got {value!r}")
    return value


def node_upsert_query(label: str) -> str:
    _identifier(label, "node label")
    return (
        "UNWIND $rows AS row MERGE (n {id: row.id}) "
        f"SET n:{label}, n.name = row.name, n.repo = row.repo, n.path = row.path, "
        "n.line = row.line, n.kind = row.kind"
    )


def edge_upsert_query(edge_type: str, label: str) -> str:
    _identifier(edge_type, "edge type")
    _identifier(label, "node label")
    return (
        f"UNWIND $rows AS row MATCH (s:{label} {{id: row.s}}), (d:{label} {{id: row.d}}) "
        f"MERGE (s)-[r:{edge_type} {{id: row.rid}}]->(d) "
        "SET r.file = row.file, r.line = row.line, r.confidence = row.confidence"
    )


class HydraError(RuntimeError):
    pass


class HydraClient:
    """Thin wrapper over the HTTP query API (`POST /v1/graphs/{graph}/query`)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8443",
        token: str = "local-development-token-32-bytes",
        graph: str = "default",
        namespace: str = "default",
        cell: str = "cell-0",
        timeout: float = 120.0,
    ) -> None:
        self.url = f"{base_url.rstrip('/')}/v1/graphs/{graph}/query"
        self.cell = cell
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Graph-Namespace": namespace,
                "Content-Type": "application/json",
            },
        )

    def query(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
        consistency: str | None = None,
        retries: int = 3,
    ) -> dict:
        body: dict[str, Any] = {"cell_id": self.cell, "query": cypher}
        if parameters:
            body["parameters"] = parameters
        if consistency:
            body["consistency"] = consistency

        last: Exception | None = None
        for attempt in range(retries):
            try:
                response = self._client.post(self.url, json=body)
            except httpx.HTTPError as exc:  # transport-level, worth retrying
                last = exc
                time.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code == 200:
                return response.json()
            if response.status_code in (429, 503):
                time.sleep(1.0 * (attempt + 1))
                last = HydraError(response.text[:300])
                continue
            raise HydraError(f"{response.status_code}: {response.text[:500]}\nquery: {cypher[:200]}")
        raise HydraError(f"query failed after {retries} attempts: {last}")

    def scalar(self, cypher: str, parameters: dict[str, Any] | None = None) -> Any:
        rows = self.query(cypher, parameters)["rows"]
        return rows[0][0]["value"] if rows else None

    def close(self) -> None:
        self._client.close()


class Writer:
    """Writes nodes and edges in batches, reporting progress."""

    def __init__(self, client: HydraClient, label: str = "Sym") -> None:
        self.client = client
        self.label = label

    def write_nodes(self, rows: Sequence[dict]) -> int:
        query = node_upsert_query(self.label)
        written = 0
        for batch in chunked(rows):
            self.client.query(query, {"rows": batch})
            written += len(batch)
        return written

    def write_edges(self, edge_type: str, rows: Sequence[dict]) -> int:
        query = edge_upsert_query(edge_type, self.label)
        written = 0
        for batch in chunked(rows):
            self.client.query(query, {"rows": batch})
            written += len(batch)
        return written
