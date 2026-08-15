from server.ranking import rank_symbols

# Real shape: `JSONResponse` matches one definition in starlette plus a pile of
# unresolved stubs minted from other repos' references.
CANDIDATES = [
    {"id": 24848, "name": "JSONResponse", "repo": "", "path": "", "line": -1},
    {"id": 26689, "name": "JSONResponse", "repo": "starlette", "path": "starlette/starlette/responses.py", "line": 181},
    {"id": 28110, "name": "JSONResponse", "repo": "starlette", "path": "starlette/docs/responses.md", "line": 4},
    {"id": 31000, "name": "JSONResponseFactory", "repo": "fastapi", "path": "fastapi/fastapi/responses.py", "line": 9},
]


def test_a_real_definition_outranks_an_unresolved_stub():
    # blindfold: example — 26689 is the only candidate with a repo and a .py source file.
    assert rank_symbols(CANDIDATES, "JSONResponse")[0]["id"] == 26689


def test_source_files_outrank_documentation_mentions():
    """A `.md` node is a mention, not the thing you are about to change."""
    ranked = [s["id"] for s in rank_symbols(CANDIDATES, "JSONResponse")]
    assert ranked.index(26689) < ranked.index(28110)


def test_exact_name_matches_outrank_prefix_matches():
    ranked = [s["id"] for s in rank_symbols(CANDIDATES, "JSONResponse")]
    assert ranked.index(26689) < ranked.index(31000)


def test_stubs_are_kept_but_last_because_they_are_still_valid_ids():
    ranked = [s["id"] for s in rank_symbols(CANDIDATES, "JSONResponse")]
    # blindfold: example — 24848 is the stub (no repo, no path) in the fixture.
    assert ranked[-1] == 24848


def test_ranking_is_stable_for_an_empty_candidate_list():
    assert rank_symbols([], "anything") == []
