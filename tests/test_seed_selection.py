from server.diff import select_seeds

CANDIDATES = {
    "RequestBodyLimitMiddleware": [
        {"id": 1, "name": "RequestBodyLimitMiddleware", "repo": "starlette", "path": "starlette/starlette/middleware/limits.py"},
    ],
    "__init__": [
        {"id": 2, "name": "__init__.py", "repo": "fastapi", "path": "fastapi/fastapi/__init__.py"},
    ],
    "app": [
        {"id": 3, "name": "app()", "repo": "fastapi", "path": "fastapi/tests/test_x.py"},
        {"id": 4, "name": "app()", "repo": "starlette", "path": "starlette/tests/test_limits.py"},
    ],
    "render": [
        {"id": 5, "name": "render()", "repo": "starlette", "path": "starlette/starlette/responses.py"},
    ],
}


def test_a_symbol_defined_in_the_prs_own_repo_wins():
    """The diff came from starlette, so `app` means starlette's `app`."""
    assert select_seeds(["app"], CANDIDATES, pr_repo="starlette") == [CANDIDATES["app"][1]]


def test_dunder_names_are_dropped_because_every_class_has_them():
    """Seeding on `__init__` walks from an unrelated constructor and floods the
    blast radius with noise."""
    assert select_seeds(["__init__", "__call__"], CANDIDATES, pr_repo="starlette") == []


def test_symbols_that_only_exist_in_another_repo_are_dropped():
    """A name the PR's repo does not define is a coincidence of naming, not the
    thing that changed."""
    assert select_seeds(["__init__"], CANDIDATES, pr_repo="starlette") == []


def test_real_definitions_are_kept():
    seeds = select_seeds(
        ["RequestBodyLimitMiddleware", "render"], CANDIDATES, pr_repo="starlette"
    )
    assert [s["id"] for s in seeds] == [1, 5]


def test_an_unknown_pr_repo_falls_back_to_any_definition():
    """The PR may be from a repo outside the workspace; then the best available
    match is still better than refusing to answer."""
    seeds = select_seeds(["render"], CANDIDATES, pr_repo="some-other-repo")
    assert [s["id"] for s in seeds] == [5]
