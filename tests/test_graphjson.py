from loader.graphjson import parse_graph

# Shapes copied from real graphify output (graphify-out/graph.json on fastapi).
GRAPH = {
    "directed": False,
    "nodes": [
        {
            "id": "fastapi_routing",
            "label": "routing.py",
            "file_type": "code",
            "source_file": "fastapi/fastapi/routing.py",
            "source_location": "L1",
        },
        {
            "id": "fastapi_routing_apiroute",
            "label": "APIRoute",
            "file_type": "code",
            "source_file": "fastapi/fastapi/routing.py",
            "source_location": "L412",
        },
        # Stub node: graphify emits these with no label and no source_file.
        {"id": "eventhook", "community": 3},
    ],
    "links": [
        {
            "relation": "contains",
            "source": "fastapi_routing",
            "target": "fastapi_routing_apiroute",
            "confidence": "EXTRACTED",
            "source_file": "fastapi/fastapi/routing.py",
            "source_location": "L412",
        },
        # Cross-package import: the target is dangling — no node object exists.
        {
            "relation": "imports_from",
            "source": "fastapi_routing",
            "target": "starlette_responses",
            "confidence": "EXTRACTED",
            "source_file": "fastapi/fastapi/routing.py",
            "source_location": "L30",
        },
        # Unmapped relation — must be dropped, not guessed.
        {"relation": "teleports_to", "source": "fastapi_routing", "target": "eventhook"},
    ],
}


def parsed():
    return parse_graph(GRAPH, repo="fastapi")


def test_local_nodes_are_scoped_to_their_repo():
    node = next(n for n in parsed().nodes if n.slug == "fastapi_routing_apiroute")
    assert (node.repo, node.name, node.path, node.line) == (
        "fastapi",
        "APIRoute",
        "fastapi/fastapi/routing.py",
        412,
    )


def test_stub_nodes_without_a_label_do_not_crash_and_fall_back_to_their_slug():
    """graphify stub nodes carry only {id, community}; reading n['label'] raises."""
    node = next(n for n in parsed().nodes if n.slug == "eventhook")
    assert (node.name, node.path, node.kind) == ("eventhook", None, "external")


def test_dangling_link_targets_are_minted_as_global_external_nodes():
    """This is the cross-repo join: `starlette_responses` has no node object in
    fastapi's graph, but it is the id starlette itself uses for that module."""
    node = next(n for n in parsed().nodes if n.slug == "starlette_responses")
    assert (node.repo, node.kind) == (None, "external")


def test_local_nodes_keep_their_repo_while_externals_are_global():
    by_slug = {n.slug: n.repo for n in parsed().nodes}
    assert by_slug == {
        "fastapi_routing": "fastapi",
        "fastapi_routing_apiroute": "fastapi",
        "eventhook": None,
        "starlette_responses": None,
    }


def test_edges_carry_the_call_site_and_the_mapped_type():
    edge = next(e for e in parsed().edges if e.dst_slug == "starlette_responses")
    assert (edge.type, edge.src_repo, edge.dst_repo, edge.file, edge.line) == (
        "IMPORTS",
        "fastapi",
        None,
        "fastapi/fastapi/routing.py",
        30,
    )


def test_unmapped_relations_produce_no_edge():
    # blindfold: contract — schema.edge_type_for returns None for unknown relations,
    # and parse_graph must drop those rather than inventing a type.
    assert [e.type for e in parsed().edges] == ["CONTAINS", "IMPORTS"]


def test_confidence_is_preserved_for_display():
    # blindfold: example — graphify tags every edge EXTRACTED (read from source) or
    # INFERRED (resolved); the UI shows it, so the loader must not drop it.
    assert {e.confidence for e in parsed().edges} == {"EXTRACTED"}
