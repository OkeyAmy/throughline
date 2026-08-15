"""The LLM's job here is small and deliberately so.

Retrieval is traversal. The model never decides what is impacted — it turns a
sentence into a symbol to walk from, and turns a finished walk into a paragraph.
Every claim in that paragraph has a row behind it, and the rows come from HydraDB.

Model ids and the key come from the environment (see .env.example). Both models
were checked against the live endpoint: `meta/llama-3.3-70b-instruct` answers in
`message.content`; the nemotron reasoning model puts its answer in
`message.reasoning_content` unless you pass chat_template_kwargs={"thinking": false}.
"""

from __future__ import annotations

import json
import os
import re

import httpx

BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
CHAT_MODEL = os.environ.get("NVIDIA_CHAT_MODEL", "meta/llama-3.3-70b-instruct")


class LLMUnavailable(RuntimeError):
    """Raised when no key is configured — callers fall back to plain search."""


def available() -> bool:
    return bool(os.environ.get("NVIDIA_API_KEY"))


def _chat(messages: list[dict], max_tokens: int = 400, temperature: float = 0.2) -> str:
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise LLMUnavailable("NVIDIA_API_KEY is not set")
    response = httpx.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": CHAT_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=120,
    )
    response.raise_for_status()
    message = response.json()["choices"][0]["message"]
    return (message.get("content") or message.get("reasoning_content") or "").strip()


def extract_symbol(question: str, candidates: list[dict]) -> int | None:
    """Pick which candidate symbol a plain-English question is about.

    The model chooses from ids the graph already returned; it cannot invent one.
    Returns None when nothing fits, which the caller reports rather than guessing.
    """
    if not candidates:
        return None
    listing = "\n".join(
        f"{c['id']}: {c['name']} in {c['repo'] or 'external'} ({c['path'] or 'no file'})"
        for c in candidates[:20]
    )
    reply = _chat(
        [
            {
                "role": "system",
                "content": (
                    "You map a developer's question to exactly one candidate symbol id. "
                    "Reply with only the id, or the word none if no candidate fits."
                ),
            },
            {"role": "user", "content": f"Question: {question}\n\nCandidates:\n{listing}"},
        ],
        max_tokens=16,
    )
    match = re.search(r"\d+", reply)
    if not match:
        return None
    chosen = int(match.group())
    return chosen if any(c["id"] == chosen for c in candidates) else None


def summarise_impact(seed: dict, rows: list[dict], totals: dict, trust: dict) -> str:
    """One paragraph a reviewer can act on, grounded in rows the walk produced."""
    cross = [r for r in rows if r["cross_repo"]][:8]
    tests = [r for r in rows if r["is_test"]][:8]
    facts = {
        "changed_symbol": f"{seed['name']} ({seed['repo']}, {seed['path']})",
        "total_impacted": totals["impacted"],
        "repos": totals["repos"],
        "closure_exact": trust["exact"],
        "cross_repo_examples": [f"{r['repo']}:{r['path']}#{r['hop']}hops" for r in cross],
        "test_examples": [r["path"] for r in tests],
    }
    return _chat(
        [
            {
                "role": "system",
                "content": (
                    "You brief an engineer about to change a shared symbol. Use only the "
                    "supplied facts; never invent files or counts. Three sentences: what "
                    "the change reaches, which other repos are involved, what to run. "
                    "If closure_exact is false, say the number is a lower bound."
                ),
            },
            {"role": "user", "content": json.dumps(facts)},
        ],
        max_tokens=260,
    )
