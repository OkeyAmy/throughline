"""Normalise a graphify ``graph.json`` into rows ready for HydraDB.

graphify emits networkx node-link JSON. Two shapes matter here:

* **local nodes** — carry ``source_file``/``source_location``; they belong to the
  repo being ingested.
* **dangling link endpoints** — a link whose ``source``/``target`` has no node
  object. These are external packages and modules (``typing``, ``pytest``,
  ``starlette_responses``). They are minted as global nodes (``repo=None``),
  which is what lets one repo's import meet another repo's definition.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import edge_type_for


@dataclass(frozen=True)
class NodeRow:
    repo: str | None
    slug: str
    name: str
    path: str | None
    line: int | None
    kind: str
    confidence: str | None = None


@dataclass(frozen=True)
class EdgeRow:
    src_repo: str | None
    src_slug: str
    dst_repo: str | None
    dst_slug: str
    type: str
    file: str | None
    line: int | None
    confidence: str | None


@dataclass(frozen=True)
class ParsedGraph:
    nodes: list[NodeRow]
    edges: list[EdgeRow]


def _line(location: str | None) -> int | None:
    if not location:
        return None
    digits = "".join(ch for ch in str(location) if ch.isdigit())
    return int(digits) if digits else None


def parse_graph(graph: dict, repo: str) -> ParsedGraph:
    raw_nodes = graph.get("nodes", [])
    raw_links = graph.get("links", [])

    local: dict[str, NodeRow] = {}
    external: dict[str, NodeRow] = {}

    for node in raw_nodes:
        slug = node["id"]
        source_file = node.get("source_file")
        name = node.get("label") or slug
        if source_file:
            local[slug] = NodeRow(
                repo=repo,
                slug=slug,
                name=name,
                path=source_file,
                line=_line(node.get("source_location")),
                kind=node.get("file_type") or "code",
            )
        else:
            # A node object with no source file is a stub graphify could not place.
            external[slug] = NodeRow(
                repo=None, slug=slug, name=name, path=None, line=None, kind="external"
            )

    def resolve(slug: str) -> str | None:
        """Return the owning repo for a slug, minting an external node if unknown."""
        if slug in local:
            return repo
        if slug not in external:
            external[slug] = NodeRow(
                repo=None, slug=slug, name=slug, path=None, line=None, kind="external"
            )
        return None

    edges: list[EdgeRow] = []
    for link in raw_links:
        edge_type = edge_type_for(link.get("relation", ""))
        if edge_type is None:
            continue
        src, dst = link["source"], link["target"]
        edges.append(
            EdgeRow(
                src_repo=resolve(src),
                src_slug=src,
                dst_repo=resolve(dst),
                dst_slug=dst,
                type=edge_type,
                file=link.get("source_file"),
                line=_line(link.get("source_location")),
                confidence=link.get("confidence"),
            )
        )

    return ParsedGraph(nodes=list(local.values()) + list(external.values()), edges=edges)
