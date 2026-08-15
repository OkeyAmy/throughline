"""throughline ingest — graphify graphs -> one HydraDB organisation graph.

    python -m loader ingest --workspace workspace.yml

The workspace file lists the repos, where their graphify output lives, and which
packages each repo publishes (used for cross-repo linking).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from .crossrepo import link_external_to_providers
from .graphjson import EdgeRow, NodeRow, parse_graph
from .registry import Registry
from .schema import INVERSE_OF
from .writer import HydraClient, Writer

NODE_LABEL = "Sym"


def load_workspace(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text())


def collect(workspace: dict) -> tuple[list[NodeRow], list[EdgeRow]]:
    """Parse every repo's graph.json and add the cross-repo PROVIDES edges."""
    nodes: dict[tuple[str | None, str], NodeRow] = {}
    edges: list[EdgeRow] = []

    for repo in workspace["repos"]:
        name = repo["name"]
        graph_path = Path(repo["graph"]).expanduser()
        graph = json.loads(graph_path.read_text())
        parsed = parse_graph(graph, repo=name)
        print(f"  {name}: {len(parsed.nodes)} nodes, {len(parsed.edges)} edges")
        for node in parsed.nodes:
            key = (node.repo, node.slug)
            # A local definition always wins over an external stub of the same name.
            if key not in nodes or (node.path and not nodes[key].path):
                nodes[key] = node
        edges.extend(parsed.edges)

    provides = {repo["name"]: repo.get("provides", []) for repo in workspace["repos"]}
    externals = [n for n in nodes.values() if n.repo is None]
    locals_ = [n for n in nodes.values() if n.repo is not None]
    cross = link_external_to_providers(externals, locals_, provides)
    print(f"  cross-repo PROVIDES edges: {len(cross)}")
    edges.extend(cross)
    return list(nodes.values()), edges


def ingest(workspace_path: str, base_url: str, token: str, registry_path: str) -> None:
    workspace = load_workspace(workspace_path)
    print(f"reading {len(workspace['repos'])} repos")
    nodes, edges = collect(workspace)

    registry = Registry()
    client = HydraClient(base_url=base_url, token=token)
    writer = Writer(client, label=NODE_LABEL)

    node_rows = [
        {
            "id": registry.node_id(n.repo, n.slug),
            "name": n.name,
            "repo": n.repo or "",
            "path": n.path or "",
            "line": n.line if n.line is not None else -1,
            "kind": n.kind,
        }
        for n in nodes
    ]

    started = time.time()
    written = writer.write_nodes(node_rows)
    print(f"nodes written: {written} in {time.time() - started:.1f}s")

    # Group by edge type: the type is part of the query text, so one batch per type.
    by_type: dict[str, list[dict]] = {}
    for e in edges:
        forward = {
            "s": registry.node_id(e.src_repo, e.src_slug),
            "d": registry.node_id(e.dst_repo, e.dst_slug),
            "rid": registry.edge_id(),
            "file": e.file or "",
            "line": e.line if e.line is not None else -1,
            "confidence": e.confidence or "",
        }
        by_type.setdefault(e.type, []).append(forward)
        inverse = INVERSE_OF.get(e.type)
        if inverse:
            by_type.setdefault(inverse, []).append(
                {**forward, "s": forward["d"], "d": forward["s"], "rid": registry.edge_id()}
            )

    started = time.time()
    total = 0
    for edge_type, rows in sorted(by_type.items()):
        count = writer.write_edges(edge_type, rows)
        total += count
        print(f"  {edge_type}: {count}")
    elapsed = time.time() - started
    print(f"edges written: {total} in {elapsed:.1f}s ({total / max(elapsed, 1e-9):.0f}/s)")

    registry.save(registry_path)
    print(f"registry saved to {registry_path}")
    client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="throughline")
    sub = parser.add_subparsers(dest="command", required=True)

    ing = sub.add_parser("ingest", help="load graphify output into HydraDB")
    ing.add_argument("--workspace", default="workspace.yml")
    ing.add_argument("--base-url", default="http://127.0.0.1:8443")
    ing.add_argument("--token", default="local-development-token-32-bytes")
    ing.add_argument("--registry", default="registry.json")

    args = parser.parse_args(argv)
    if args.command == "ingest":
        ingest(args.workspace, args.base_url, args.token, args.registry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
