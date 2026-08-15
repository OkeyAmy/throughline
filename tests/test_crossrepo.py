from loader.crossrepo import link_external_to_providers
from loader.graphjson import NodeRow

STARLETTE_RESPONSES = NodeRow(
    repo="starlette",
    slug="starlette_responses",
    name="responses.py",
    path="starlette/starlette/responses.py",
    line=1,
    kind="code",
)
STARLETTE_UUID_STUB = NodeRow(
    repo="starlette", slug="uuid", name="uuid", path=None, line=None, kind="external"
)
EXTERNAL_RESPONSES = NodeRow(
    repo=None, slug="starlette_responses", name="starlette_responses", path=None, line=None, kind="external"
)
EXTERNAL_UUID = NodeRow(repo=None, slug="uuid", name="uuid", path=None, line=None, kind="external")
EXTERNAL_PYTEST = NodeRow(repo=None, slug="pytest", name="pytest", path=None, line=None, kind="external")

PROVIDES = {"starlette": ["starlette"]}


def test_an_external_module_links_to_the_repo_that_defines_it():
    edges = link_external_to_providers(
        externals=[EXTERNAL_RESPONSES],
        local_nodes=[STARLETTE_RESPONSES],
        provides=PROVIDES,
    )
    assert [(e.src_slug, e.dst_repo, e.dst_slug, e.type) for e in edges] == [
        ("starlette_responses", "starlette", "starlette_responses", "PROVIDES")
    ]


def test_externals_nobody_publishes_are_left_unlinked():
    """`pytest` is a real dependency but no repo in this workspace provides it;
    inventing an edge would put third-party code inside the blast radius."""
    edges = link_external_to_providers(
        externals=[EXTERNAL_PYTEST], local_nodes=[STARLETTE_RESPONSES], provides=PROVIDES
    )
    assert edges == []


def test_a_name_collision_outside_the_package_namespace_is_not_linked():
    """starlette's own graph contains a stub node called `uuid`. Linking the global
    `uuid` external to it would splice the stdlib into the graph as if starlette
    published it."""
    edges = link_external_to_providers(
        externals=[EXTERNAL_UUID],
        local_nodes=[STARLETTE_RESPONSES, STARLETTE_UUID_STUB],
        provides=PROVIDES,
    )
    assert edges == []


def test_only_nodes_with_a_real_source_file_can_provide():
    """A stub target proves nothing about where the code lives."""
    starlette_stub = NodeRow(
        repo="starlette", slug="starlette_responses", name="x", path=None, line=None, kind="external"
    )
    edges = link_external_to_providers(
        externals=[EXTERNAL_RESPONSES], local_nodes=[starlette_stub], provides=PROVIDES
    )
    assert edges == []


def test_the_package_root_itself_links():
    root = NodeRow(
        repo="starlette",
        slug="starlette",
        name="__init__.py",
        path="starlette/starlette/__init__.py",
        line=1,
        kind="code",
    )
    external_root = NodeRow(
        repo=None, slug="starlette", name="starlette", path=None, line=None, kind="external"
    )
    edges = link_external_to_providers(
        externals=[external_root], local_nodes=[root], provides=PROVIDES
    )
    assert [e.dst_slug for e in edges] == ["starlette"]
