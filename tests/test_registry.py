from loader.registry import EDGE_ID_BASE, Registry


def test_same_symbol_in_same_repo_gets_same_id():
    reg = Registry()
    assert reg.node_id("fastapi", "fastapi_routing") == reg.node_id("fastapi", "fastapi_routing")


def test_same_slug_in_different_repos_gets_different_ids():
    reg = Registry()
    assert reg.node_id("fastapi", "utils") != reg.node_id("starlette", "utils")


def test_external_symbols_are_global_across_repos():
    """The cross-repo join depends on this: an external name means the same node
    no matter which repo referenced it."""
    reg = Registry()
    assert reg.node_id(None, "starlette_responses") == reg.node_id(None, "starlette_responses")
    assert reg.node_id(None, "starlette_responses") != reg.node_id("fastapi", "starlette_responses")


def test_node_ids_are_allocated_from_zero_upward():
    # blindfold: contract — HydraDB vertex ids must be non-negative integers, so the
    # registry hands them out densely from 0 (claude.md §3.1).
    reg = Registry()
    assert [reg.node_id("repo", s) for s in ("a", "b", "c")] == [0, 1, 2]


def test_edge_ids_start_above_the_node_id_space():
    # blindfold: contract — edge ids are kept disjoint from node ids so a mixed-up
    # id can never silently address the wrong entity.
    reg = Registry()
    assert reg.edge_id() == EDGE_ID_BASE
    assert reg.edge_id() == EDGE_ID_BASE + 1


def test_edge_ids_never_repeat():
    reg = Registry()
    edges = [reg.edge_id() for _ in range(50)]
    # blindfold: invariant — 50 allocations must yield 50 distinct ids.
    assert len(set(edges)) == 50


def test_registry_survives_save_and_load(tmp_path):
    path = tmp_path / "registry.json"
    reg = Registry()
    nid = reg.node_id("fastapi", "fastapi_routing")
    last_edge = reg.edge_id()
    reg.save(path)

    reloaded = Registry.load(path)
    assert reloaded.node_id("fastapi", "fastapi_routing") == nid
    assert reloaded.edge_id() == last_edge + 1


def test_reverse_lookup_returns_repo_and_slug():
    reg = Registry()
    nid = reg.node_id("fastapi", "fastapi_routing")
    assert reg.lookup(nid) == ("fastapi", "fastapi_routing")
