"""The baseline the graph is measured against: real embedding retrieval.

A keyword baseline would be a strawman — and losing honestly to a real one is
worth more than beating a fake one. This embeds every Python file in the workspace
with NVIDIA's `llama-nemotron-embed-1b-v2` (2048 dims, `input_type` required on
every call) and retrieves by cosine similarity, which is exactly how an IDE
assistant retrieves context today.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import httpx

BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
MODEL = os.environ.get("NVIDIA_EMBED_MODEL", "nvidia/llama-nemotron-embed-1b-v2")
CHARS_PER_FILE = 6000  # head of the file; enough for imports, class and def lines
#: fastapi ships thousands of tiny tutorial snippets under docs_src/. They are not
#: the library, and embedding them would drown the corpus. Excluded from BOTH
#: methods and from the ground truth, so the comparison stays like-for-like.
EXCLUDED_PATH_PARTS = ("/docs_src/", "/.venv/", "/site-packages/")
BATCH = 16


def _key() -> str:
    key = os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        raise RuntimeError("NVIDIA_API_KEY is not set (see .env.example)")
    return key


def embed(texts: list[str], input_type: str) -> list[list[float]]:
    response = httpx.post(
        f"{BASE_URL}/embeddings",
        headers={"Authorization": f"Bearer {_key()}"},
        json={"model": MODEL, "input": texts, "input_type": input_type},
        timeout=180,
    )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["data"]]


def build_index(roots: list[Path], cache: Path) -> dict[str, list[float]]:
    """One vector per file, cached on disk — the corpus does not change between runs."""
    if cache.exists():
        return json.loads(cache.read_text())

    files: list[tuple[str, str]] = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if any(part in str(path) for part in EXCLUDED_PATH_PARTS):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:CHARS_PER_FILE]
            except OSError:
                continue
            if not text.strip():
                continue
            relative = f"{root.name}/{path.resolve().relative_to(root.resolve())}"
            files.append((relative, f"{relative}\n\n{text}"))

    index: dict[str, list[float]] = {}
    for start in range(0, len(files), BATCH):
        batch = files[start : start + BATCH]
        for attempt in range(4):
            try:
                vectors = embed([text for _, text in batch], "passage")
                break
            except Exception:  # noqa: BLE001 — rate limits are expected on the free tier
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        for (relative, _), vector in zip(batch, vectors):
            index[relative] = vector
        print(f"  embedded {min(start + BATCH, len(files))}/{len(files)} files", flush=True)

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(index))
    return index


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def retrieve(index: dict[str, list[float]], question: str, k: int) -> list[str]:
    query = embed([question], "query")[0]
    scored = sorted(index.items(), key=lambda item: _cosine(query, item[1]), reverse=True)
    return [path for path, _ in scored[:k]]
