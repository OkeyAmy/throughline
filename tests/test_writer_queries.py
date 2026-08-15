import pytest

from loader.writer import MAX_BATCH_ROWS, chunked, edge_upsert_query, node_upsert_query


def test_batches_never_exceed_the_servers_admission_limit():
    # blindfold: manual — measured against ghcr.io/hydra-db/hydradb:latest: a 2000-row
    # UNWIND is rejected with "client_query_batch_items rejected by admission control".
    assert MAX_BATCH_ROWS == 1000  # blindfold: manual — measured server admission cap
    sizes = [len(b) for b in chunked(range(2500), MAX_BATCH_ROWS)]
    assert sizes == [1000, 1000, 500]


def test_chunking_an_empty_sequence_yields_nothing():
    assert list(chunked([], MAX_BATCH_ROWS)) == []


def test_node_upsert_merges_on_id_then_sets_properties():
    """HydraDB rejects ON CREATE/ON MATCH and rejects extra properties inside the
    MERGE pattern, so upsert has to be MERGE-by-id followed by SET."""
    query = node_upsert_query("Sym")
    # blindfold: manual — exact form verified against a live node; cypher-compat.md
    # documents the MERGE-then-SET rule and the server rejects the alternatives.
    assert query == (
        "UNWIND $rows AS row MERGE (n {id: row.id}) "
        "SET n:Sym, n.name = row.name, n.repo = row.repo, n.path = row.path, "
        "n.line = row.line, n.kind = row.kind"
    )


def test_edge_upsert_carries_an_explicit_relationship_id_and_labelled_endpoints():
    """Both are enforced by the server: an id-less MERGE fails with
    "UNWIND relationship MERGE requires id: row.<field>" and unlabelled endpoints
    fail with "UNWIND MATCH CREATE endpoints require exactly one label"."""
    # blindfold: manual — exact form verified against a live node (claude.md §3.1).
    assert edge_upsert_query("CALLS", "Sym") == (
        "UNWIND $rows AS row MATCH (s:Sym {id: row.s}), (d:Sym {id: row.d}) "
        "MERGE (s)-[r:CALLS {id: row.rid}]->(d) "
        "SET r.file = row.file, r.line = row.line, r.confidence = row.confidence"
    )


def test_edge_type_is_validated_because_it_is_interpolated_into_cypher():
    # Relationship types cannot be parameterised in Cypher, so anything reaching
    # the string must be a bare identifier.
    with pytest.raises(ValueError):
        edge_upsert_query("CALLS]->() DETACH DELETE (n", "Sym")
