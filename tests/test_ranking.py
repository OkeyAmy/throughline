from server.ranking import rank_impact

INFO = {
    10: {"id": 10, "name": "Response", "repo": "starlette", "path": "starlette/responses.py", "line": 40},
    11: {"id": 11, "name": "routing.py", "repo": "fastapi", "path": "fastapi/routing.py", "line": 1},
    12: {"id": 12, "name": "starlette_responses", "repo": "external", "path": "", "line": -1},
    13: {"id": 13, "name": "test_responses.py", "repo": "starlette", "path": "starlette/tests/test_responses.py", "line": 1},
}


def test_rows_are_ordered_by_hop_distance():
    rows = rank_impact({10: 2, 11: 1}, INFO, seed_repo="starlette")
    assert [r["id"] for r in rows] == [11, 10]


def test_cross_repo_rows_come_first_within_a_hop():
    """A caller in another repo is the finding; a caller next door is expected."""
    rows = rank_impact({10: 1, 11: 1}, INFO, seed_repo="starlette")
    assert [r["id"] for r in rows] == [11, 10]


def test_cross_repo_rows_are_flagged():
    rows = rank_impact({10: 1, 11: 1}, INFO, seed_repo="starlette")
    assert {r["id"]: r["cross_repo"] for r in rows} == {11: True, 10: False}


def test_external_plumbing_nodes_are_not_shown_as_impacted_code():
    """External stubs are the joint between two repos, not a place anything breaks.
    They stay in the evidence path, out of the impact list."""
    rows = rank_impact({12: 1, 10: 2}, INFO, seed_repo="starlette")
    assert [r["id"] for r in rows] == [10]


def test_tests_are_marked_so_the_user_knows_what_to_run():
    rows = rank_impact({13: 1}, INFO, seed_repo="starlette")
    assert rows[0]["is_test"] is True


def test_non_test_source_files_are_not_marked_as_tests():
    rows = rank_impact({11: 1}, INFO, seed_repo="starlette")
    assert rows[0]["is_test"] is False


def test_rows_carry_what_the_ui_renders():
    rows = rank_impact({11: 1}, INFO, seed_repo="starlette")
    assert rows[0] == {
        "id": 11,
        "name": "routing.py",
        "repo": "fastapi",
        "path": "fastapi/routing.py",
        "line": 1,
        "hop": 1,
        "cross_repo": True,
        "is_test": False,
    }
