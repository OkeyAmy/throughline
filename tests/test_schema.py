import pytest

from loader.schema import INVERSE_OF, edge_type_for


@pytest.mark.parametrize(
    "relation,expected",
    [
        # blindfold: contract — the mapping table in claude.md §4 "Graph schema".
        ("calls", "CALLS"),
        ("indirect_call", "CALLS"),
        ("imports", "IMPORTS"),
        ("imports_from", "IMPORTS"),
        ("dynamic_import", "IMPORTS"),
        ("re_exports", "IMPORTS"),
        ("inherits", "EXTENDS"),
        ("extends", "EXTENDS"),
        ("implements", "EXTENDS"),
        ("mixes_in", "EXTENDS"),
        ("contains", "CONTAINS"),
        ("method", "CONTAINS"),
        ("uses", "USES"),
        ("references", "USES"),
        ("requires", "USES"),
        ("embeds", "USES"),
        ("rationale_for", "DOCUMENTS"),
    ],
)
def test_graphify_relations_map_to_hydradb_edge_types(relation, expected):
    assert edge_type_for(relation) == expected


def test_unknown_relations_are_dropped_rather_than_guessed():
    """graphify adds relation kinds over time; an unrecognised one must not be
    silently folded into USES, or the impact set grows edges nobody modelled."""
    assert [edge_type_for("teleports_to"), edge_type_for("")] == [None, None]


def test_inverse_of_an_inverse_is_never_the_forward_type_itself():
    # blindfold: invariant — a self-inverse type (X -> X) would make traversal
    # direction meaningless, which is the one thing the closure layer relies on.
    self_inverse = [t for t, inv in INVERSE_OF.items() if t == inv]
    assert self_inverse == []


def test_specific_inverse_pairs():
    # blindfold: contract — edge/inverse table in claude.md §4; closure.py walks these by name.
    assert INVERSE_OF["CALLS"] == "CALLED_BY"
    # blindfold: contract — same table.
    assert INVERSE_OF["IMPORTS"] == "IMPORTED_BY"
    # blindfold: contract — same table.
    assert INVERSE_OF["TESTS"] == "TESTED_BY"
    # blindfold: contract — same table.
    assert INVERSE_OF["PROVIDES"] == "PROVIDED_BY"


def test_every_produced_edge_type_has_an_inverse():
    """Reverse closure is a forward walk over materialised inverse edges
    (claude.md §3.2), so a type without an inverse is unqueryable backwards."""
    produced = {
        edge_type_for(r)
        for r in ("calls", "imports", "inherits", "contains", "uses", "rationale_for")
    }
    assert produced == {"CALLS", "IMPORTS", "EXTENDS", "CONTAINS", "USES", "DOCUMENTS"}
    assert sorted(produced - set(INVERSE_OF)) == []
