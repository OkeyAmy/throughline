"""Ground truth that does not come from our own graph.

For a symbol, the files that actually mention it — read straight out of the source
with ripgrep, word-boundary matched. It is a blunt instrument (a comment counts, a
same-named local counts) but it is *independent*: neither the graph nor the
embedding baseline had any hand in producing it, which is the whole point. Scoring
our own retriever against our own extractor would prove nothing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def referencing_files(symbol: str, roots: list[Path], exclude_path: str | None = None) -> set[str]:
    """Repo-relative paths of Python files that mention `symbol`."""
    if not symbol or not symbol.replace("_", "").isalnum():
        return set()

    found: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        result = subprocess.run(
            ["rg", "--files-with-matches", "--word-regexp", "--type", "py", "--", symbol, str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            path = _normalise(line, root)
            if path and path != exclude_path:
                found.add(path)
    return found


def _normalise(line: str, root: Path) -> str | None:
    """`.repos/starlette/starlette/responses.py` -> `starlette/starlette/responses.py`.

    The graph stores paths as graphify saw them: prefixed by the repo directory
    name, not the checkout location.
    """
    try:
        relative = Path(line).resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return f"{root.name}/{relative}"
