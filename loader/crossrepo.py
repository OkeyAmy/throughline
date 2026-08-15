"""Cross-repo linking.

graphify scopes node ids to module paths, so ``from starlette.responses import
JSONResponse`` inside fastapi produces an edge to the dangling id
``starlette_responses`` — which is exactly the id starlette uses for that module
in its own graph. Linking the two is what turns several repo graphs into one
organisation graph.

The link is config-driven (``repos.yml``: repo -> packages it publishes) rather
than inferred from registry metadata. Import-name to distribution-name resolution
is a genuinely hard problem (``import yaml`` -> ``PyYAML``) and guessing it wrong
produces a graph that looks connected but isn't.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from .graphjson import EdgeRow, NodeRow


def link_external_to_providers(
    externals: Iterable[NodeRow],
    local_nodes: Iterable[NodeRow],
    provides: Mapping[str, Sequence[str]],
) -> list[EdgeRow]:
    """Return PROVIDES edges from external stubs to the repo nodes that define them."""
    # slug -> node, restricted to real definitions (a stub cannot provide anything)
    definitions = {n.slug: n for n in local_nodes if n.repo and n.path}

    owner_of_package = {pkg: repo for repo, packages in provides.items() for pkg in packages}

    edges: list[EdgeRow] = []
    for external in externals:
        slug = external.slug
        package = _owning_package(slug, owner_of_package)
        if package is None:
            continue
        definition = definitions.get(slug)
        if definition is None or definition.repo != owner_of_package[package]:
            continue
        edges.append(
            EdgeRow(
                src_repo=None,
                src_slug=slug,
                dst_repo=definition.repo,
                dst_slug=definition.slug,
                type="PROVIDES",
                file=definition.path,
                line=definition.line,
                confidence="INFERRED",
            )
        )
    return edges


def _owning_package(slug: str, owner_of_package: Mapping[str, str]) -> str | None:
    """The package whose namespace this slug sits in, or None.

    ``starlette_responses`` belongs to ``starlette``; ``uuid`` belongs to nobody,
    even when some repo happens to contain a stub node with that name.
    """
    for package in owner_of_package:
        if slug == package or slug.startswith(f"{package}_"):
            return package
    return None
