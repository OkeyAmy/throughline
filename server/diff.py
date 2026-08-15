"""Turn a pull request into seeds for the walk.

A reviewer does not think in symbols, they think in diffs. This reads the changed
hunks, pulls out the definitions they touch, and hands those to the closure as
seeds — so "what does this PR reach" is the same question as "what does this
symbol reach", asked several times at once.

Only definition lines count. A hunk that merely mentions a name changes nothing
about that name's contract, and seeding on every identifier in a diff would make
the blast radius meaningless.
"""

from __future__ import annotations

import re

import httpx

PR_URL = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")

CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx")

# `def name(`, `class Name(`, `async def name(` — with or without the diff's +/-.
DEFINITION = re.compile(
    r"^[+-]\s*(?:async\s+)?(?:def|class|function)\s+([A-Za-z_][A-Za-z0-9_]*)"
)


def parse_pr_url(url: str) -> tuple[str, str, int] | None:
    match = PR_URL.search(url or "")
    if not match:
        return None
    owner, repo, number = match.groups()
    return owner, repo, int(number)


def fetch_diff(owner: str, repo: str, number: int, timeout: float = 30.0) -> str:
    """Public PRs only — no token, so no credentials live in this service."""
    response = httpx.get(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
        headers={"Accept": "application/vnd.github.v3.diff"},
        timeout=timeout,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def changed_symbols(diff: str) -> set[str]:
    symbols: set[str] = set()
    in_code_file = False

    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            in_code_file = line.rstrip().endswith(CODE_SUFFIXES)
            continue
        if not in_code_file or line.startswith(("+++", "---")):
            continue
        match = DEFINITION.match(line)
        if match:
            symbols.add(match.group(1))
    return symbols


_STOPWORDS = {
    "what", "who", "which", "where", "when", "how", "does", "the", "and", "for",
    "this", "that", "change", "changes", "breaks", "break", "calls", "uses",
    "tests", "test", "code", "function", "class", "module", "repo", "happens",
    "impact", "would", "should", "could", "about", "into", "there", "with",
}


def first_identifier(question: str) -> str:
    """The word in a question most likely to name code — used as a search prefix.

    Deterministic on purpose: the symbol shortlist comes from the graph, and the
    model only picks between candidates it produced (server/llm.py).
    """
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", question or "")
    words = [w for w in words if len(w) > 2 and w.lower() not in _STOPWORDS]
    return max(words, key=len) if words else (question or "").strip()


def select_seeds(
    names: list[str], candidates: dict[str, list[dict]], pr_repo: str
) -> list[dict]:
    """Choose which changed names are worth walking from.

    Two rules, both learned from a real PR: dunder methods are defined by every
    class in the workspace and seeding on one floods the answer, and a name the
    PR's own repo does not define is a naming coincidence rather than the thing
    that changed.
    """
    seeds: list[dict] = []
    for name in names:
        if name.startswith("__") and name.endswith("__"):
            continue
        matches = [c for c in candidates.get(name, []) if c.get("repo")]
        if not matches:
            continue
        same_repo = [c for c in matches if c["repo"] == pr_repo]
        if same_repo:
            seeds.append(same_repo[0])
        elif pr_repo not in {c["repo"] for c in candidates_repos(candidates)}:
            # The PR is from a repo outside the workspace: any definition beats none.
            seeds.append(matches[0])
    return seeds


def candidates_repos(candidates: dict[str, list[dict]]) -> list[dict]:
    return [c for group in candidates.values() for c in group]
