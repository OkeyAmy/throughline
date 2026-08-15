from server.diff import changed_symbols, parse_pr_url

DIFF = """diff --git a/starlette/responses.py b/starlette/responses.py
index 1111111..2222222 100644
--- a/starlette/responses.py
+++ b/starlette/responses.py
@@ -178,7 +178,7 @@ class Response:
     def render(self, content: typing.Any) -> bytes:
-class JSONResponse(Response):
+class JSONResponse(Response, extra=True):
     media_type = "application/json"
@@ -200,6 +200,9 @@ class JSONResponse(Response):
+    def render_fast(self, content: typing.Any) -> bytes:
+        return b""
diff --git a/docs/responses.md b/docs/responses.md
--- a/docs/responses.md
+++ b/docs/responses.md
@@ -1,3 +1,3 @@
-old text
+new text
"""


def test_a_pr_url_yields_owner_repo_and_number():
    assert parse_pr_url("https://github.com/encode/starlette/pull/2612") == (
        "encode",
        "starlette",
        2612,
    )


def test_urls_that_are_not_pull_requests_are_rejected():
    rejected = [
        parse_pr_url("https://github.com/encode/starlette"),
        parse_pr_url("https://github.com/encode/starlette/issues/12"),
        parse_pr_url("JSONResponse"),
    ]
    assert rejected == [None, None, None]


def test_changed_classes_and_functions_are_extracted_from_the_diff():
    assert changed_symbols(DIFF) == {"JSONResponse", "render_fast"}


def test_prose_files_contribute_no_symbols():
    """A docs-only hunk must not seed a walk — every name in it would be noise."""
    docs_only = DIFF.split("diff --git a/docs/responses.md")[1]
    assert changed_symbols("diff --git a/docs/responses.md" + docs_only) == set()


def test_removed_definitions_count_too():
    """Deleting a function breaks its callers just as surely as changing it."""
    removal = (
        "diff --git a/x/y.py b/x/y.py\n--- a/x/y.py\n+++ b/x/y.py\n"
        "@@ -1,3 +1,2 @@\n-def gone_now(arg):\n-    return 1\n"
    )
    assert changed_symbols(removal) == {"gone_now"}


def test_an_empty_diff_yields_nothing_rather_than_failing():
    assert changed_symbols("") == set()
