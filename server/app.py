"""throughline HTTP service.

Every answer carries its own provenance: whether the closure was exact, how deep
it went, how many round trips it cost HydraDB and how long it took. An impact
answer that quietly dropped callers is a wrong answer, so the UI is told which
one it got.
"""

from __future__ import annotations

import json
import os
import time
from queue import Queue
from threading import Thread
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from loader.writer import HydraClient
from server.closure import closure
from server.hydra import (
    IMPACT_INVERSE_EDGES,
    HydraExpander,
    evidence_paths,
    find_symbols,
    hydrate,
    paths_between,
)
from server.diff import (
    changed_symbols,
    fetch_diff,
    first_identifier,
    parse_pr_url,
    select_seeds,
)
from server.ranking import rank_impact
from server import llm
from eval_harness.embed_baseline import retrieve as embed_retrieve

HYDRA_URL = os.environ.get("HYDRADB_URL", "http://127.0.0.1:8443")
HYDRA_TOKEN = os.environ.get("HYDRADB_TOKEN", "local-development-token-32-bytes")
MAX_WORKERS = int(os.environ.get("THROUGHLINE_WORKERS", "6"))

app = FastAPI(title="throughline", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def summarise_rows(all_rows: list[dict], impacted: int, shown: int) -> dict:
    """Totals over the whole closure, not over the page of rows being displayed.

    Counting only the visible rows understates the answer — and the understatement
    lands in the headline number, which is the one a reviewer acts on.
    """
    repos: dict[str, int] = {}
    for row in all_rows:
        repos[row["repo"]] = repos.get(row["repo"], 0) + 1
    return {
        "impacted": impacted,
        "shown": shown,
        "in_repos": len(repos),
        "repos": dict(sorted(repos.items(), key=lambda kv: -kv[1])),
        "tests": sum(1 for r in all_rows if r["is_test"]),
        "cross_repo": sum(1 for r in all_rows if r["cross_repo"]),
    }


def client() -> HydraClient:
    return HydraClient(base_url=HYDRA_URL, token=HYDRA_TOKEN)


class ImpactRequest(BaseModel):
    symbol_id: int | None = None
    symbol: str | None = None
    max_depth: int = 12  # deep enough that the walk usually exhausts rather than caps
    node_cap: int = 20000
    limit: int = 200


@app.get("/api/health")
def health() -> dict:
    c = client()
    try:
        nodes = c.scalar("MATCH (n:Sym) RETURN count(*) AS c")
        return {"ok": True, "hydradb": HYDRA_URL, "nodes": nodes}
    except Exception as exc:  # surfaced in the UI rather than swallowed
        raise HTTPException(status_code=503, detail=f"HydraDB unreachable: {exc}") from exc
    finally:
        c.close()


@app.get("/api/symbols")
def symbols(q: str, limit: int = 20) -> dict:
    c = client()
    try:
        return {"symbols": find_symbols(c, q, limit=limit)}
    finally:
        c.close()


@app.post("/api/impact")
def impact(request: ImpactRequest) -> dict:
    c = client()
    try:
        seed_id = request.symbol_id
        if seed_id is None:
            if not request.symbol:
                raise HTTPException(status_code=400, detail="symbol_id or symbol is required")
            matches = [s for s in find_symbols(c, request.symbol, limit=25) if s.get("repo")]
            if not matches:
                raise HTTPException(status_code=404, detail=f"no symbol matching {request.symbol!r}")
            seed_id = matches[0]["id"]

        seed_info = hydrate(c, [seed_id])[int(seed_id)]

        started = time.perf_counter()
        expander = HydraExpander(c)
        result = closure(
            expander,
            seeds=[int(seed_id)],
            edge_types=list(IMPACT_INVERSE_EDGES),
            max_depth=request.max_depth,
            node_cap=request.node_cap,
            max_workers=MAX_WORKERS,
        )
        walk_ms = (time.perf_counter() - started) * 1000

        info = hydrate(c, list(result.hops))
        all_rows = rank_impact(result.hops, info, seed_repo=seed_info.get("repo", ""))
        rows = all_rows[: request.limit]
        totals = summarise_rows(all_rows, len(result.hops), len(rows))

        return {
            "seed": seed_info,
            "rows": rows,
            "totals": totals,
            "trust": {
                "exact": result.exact,
                "truncated_by": result.truncated_by,
                "depth": result.depth_reached,
                "max_depth": request.max_depth,
                "round_trips": result.round_trips,
                "ms": round(walk_ms),
                "edge_types": list(IMPACT_INVERSE_EDGES),
                "engine": "batched BFS over materialised inverse edges (HydraDB)",
            },
        }
    finally:
        c.close()


@app.get("/api/impact/stream")
def impact_stream(symbol_id: int, max_depth: int = 12, limit: int = 200) -> StreamingResponse:
    """The same walk, emitted level by level.

    Each event is one BFS level that HydraDB actually served, so the UI shows the
    frontier expanding hop by hop instead of a spinner. Same numbers as /api/impact.
    """

    def events():
        c = client()
        try:
            seed_info = hydrate(c, [symbol_id])[int(symbol_id)]
            yield _sse("seed", seed_info)

            # The walk runs on its own thread and pushes each completed level onto a
            # queue, so the client sees a hop land the moment HydraDB serves it —
            # collecting levels first and emitting afterwards would not be streaming.
            queue: Queue = Queue()
            started = time.perf_counter()

            def run() -> None:
                try:
                    queue.put(
                        (
                            "result",
                            closure(
                                HydraExpander(c),
                                seeds=[int(symbol_id)],
                                edge_types=list(IMPACT_INVERSE_EDGES),
                                max_depth=max_depth,
                                max_workers=MAX_WORKERS,
                                on_level=lambda level: queue.put(
                                    (
                                        "level",
                                        {
                                            "depth": level.depth,
                                            "discovered": len(level.discovered),
                                            "total": level.total,
                                            "round_trips": level.round_trips,
                                            "frontier": level.frontier_size,
                                        },
                                    )
                                ),
                            ),
                        )
                    )
                except Exception as exc:  # noqa: BLE001 — forwarded to the client
                    queue.put(("failed", exc))

            worker = Thread(target=run, daemon=True)
            worker.start()

            result = None
            while True:
                kind, payload = queue.get()
                if kind == "level":
                    yield _sse("level", payload)
                elif kind == "failed":
                    raise payload
                else:
                    result = payload
                    break

            walk_ms = (time.perf_counter() - started) * 1000
            info = hydrate(c, list(result.hops))
            all_rows = rank_impact(result.hops, info, seed_repo=seed_info.get("repo", ""))
            rows = all_rows[:limit]
            totals = summarise_rows(all_rows, len(result.hops), len(rows))

            yield _sse(
                "done",
                {
                    "rows": rows,
                    "totals": totals,
                    "trust": {
                        "exact": result.exact,
                        "truncated_by": result.truncated_by,
                        "depth": result.depth_reached,
                        "max_depth": max_depth,
                        "round_trips": result.round_trips,
                        "ms": round(walk_ms),
                        "edge_types": list(IMPACT_INVERSE_EDGES),
                        "engine": "batched BFS over materialised inverse edges (HydraDB)",
                    },
                },
            )
        except Exception as exc:  # the UI shows the failure rather than hanging
            yield _sse("error", {"message": str(exc)[:400]})
        finally:
            c.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


class PRRequest(BaseModel):
    url: str
    max_depth: int = 12
    limit: int = 200


@app.post("/api/impact/pr")
def impact_of_pr(request: PRRequest) -> dict:
    """What a pull request reaches.

    The diff's changed definitions become the seeds of one walk — the same closure
    the single-symbol view runs, started from several points at once. Public repos
    only: no GitHub token lives in this service.
    """
    parsed = parse_pr_url(request.url)
    if parsed is None:
        raise HTTPException(status_code=400, detail="not a GitHub pull request URL")
    owner, repo, number = parsed

    try:
        diff = fetch_diff(owner, repo, number)
    except Exception as exc:  # noqa: BLE001 — network/404s are the user's problem to see
        raise HTTPException(status_code=502, detail=f"could not fetch that PR: {exc}") from exc

    names = sorted(changed_symbols(diff))
    if not names:
        return {
            "pr": {"owner": owner, "repo": repo, "number": number},
            "changed_symbols": [],
            "rows": [],
            "totals": {"impacted": 0, "shown": 0, "repos": {}, "tests": 0, "cross_repo": 0},
            "note": "no function or class definitions changed in this diff",
        }

    c = client()
    try:
        candidates = {name: find_symbols(c, name, limit=10) for name in names[:30]}
        seeds = select_seeds(names[:30], candidates, pr_repo=repo)
        if not seeds:
            raise HTTPException(
                status_code=404,
                detail=f"none of the changed symbols are in the graph: {', '.join(names[:8])}",
            )

        started = time.perf_counter()
        result = closure(
            HydraExpander(c),
            seeds=[s["id"] for s in seeds],
            edge_types=list(IMPACT_INVERSE_EDGES),
            max_depth=request.max_depth,
            max_workers=MAX_WORKERS,
        )
        walk_ms = (time.perf_counter() - started) * 1000

        seed_repo = seeds[0].get("repo", "")
        info = hydrate(c, list(result.hops))
        all_rows = rank_impact(result.hops, info, seed_repo=seed_repo)
        rows = all_rows[: request.limit]
        totals = summarise_rows(all_rows, len(result.hops), len(rows))

        return {
            "pr": {"owner": owner, "repo": repo, "number": number},
            "changed_symbols": names,
            "seeds": seeds,
            "rows": rows,
            "totals": totals,
            "trust": {
                "exact": result.exact,
                "truncated_by": result.truncated_by,
                "depth": result.depth_reached,
                "max_depth": request.max_depth,
                "round_trips": result.round_trips,
                "ms": round(walk_ms),
                "seeds": len(seeds),
                "engine": "batched BFS over materialised inverse edges (HydraDB)",
            },
        }
    finally:
        c.close()


class AskRequest(BaseModel):
    question: str
    limit: int = 60
    summarise: bool = True


@app.post("/api/ask")
def ask(request: AskRequest) -> dict:
    """Plain English in, traversal out.

    The model does two small jobs: pick which candidate symbol the question means,
    and write the summary at the end. What is impacted is decided by the walk, and
    the rows are returned alongside the prose so nothing has to be taken on faith.
    """
    c = client()
    try:
        prefix = first_identifier(request.question)
        candidates = find_symbols(c, prefix, limit=20)
        if not candidates:
            raise HTTPException(status_code=404, detail=f"nothing in the graph matches {prefix!r}")

        seed_id = None
        if llm.available():
            try:
                seed_id = llm.extract_symbol(request.question, candidates)
            except Exception:  # noqa: BLE001 — the graph answer does not depend on the model
                seed_id = None
        if seed_id is None:
            seed_id = next((s["id"] for s in candidates if s.get("repo")), candidates[0]["id"])

        seed = hydrate(c, [seed_id])[int(seed_id)]
        started = time.perf_counter()
        result = closure(
            HydraExpander(c),
            seeds=[int(seed_id)],
            edge_types=list(IMPACT_INVERSE_EDGES),
            max_depth=12,
            max_workers=MAX_WORKERS,
        )
        walk_ms = (time.perf_counter() - started) * 1000

        info = hydrate(c, list(result.hops))
        all_rows = rank_impact(result.hops, info, seed_repo=seed.get("repo", ""))
        rows = all_rows[: request.limit]
        totals = summarise_rows(all_rows, len(result.hops), len(rows))
        trust = {
            "exact": result.exact,
            "truncated_by": result.truncated_by,
            "depth": result.depth_reached,
            "round_trips": result.round_trips,
            "ms": round(walk_ms),
            "engine": "batched BFS over materialised inverse edges (HydraDB)",
            "llm_used_for": "symbol choice and summary only — never for what is impacted",
        }

        answer = None
        if request.summarise and llm.available():
            try:
                answer = llm.summarise_impact(seed, rows, totals, trust)
            except Exception as exc:  # noqa: BLE001
                answer = f"(summary unavailable: {exc})"

        return {"question": request.question, "seed": seed, "answer": answer,
                "rows": rows, "totals": totals, "trust": trust}
    finally:
        c.close()


class BaselineRequest(BaseModel):
    question: str
    k: int = 15


_BASELINE_INDEX: dict | None = None
_BASELINE_PATH = Path(__file__).resolve().parent.parent / "eval_harness" / ".embed-index.json"


@app.post("/api/baseline")
def baseline(request: BaselineRequest) -> dict:
    """The same question, answered the way an IDE assistant answers it today.

    Cosine similarity over per-file embeddings of the same corpus the graph was
    built from. It is here so the comparison in the UI is live and checkable,
    not a claim in a README — including the cases where it does well.
    """
    global _BASELINE_INDEX
    if _BASELINE_INDEX is None:
        if not _BASELINE_PATH.exists():
            raise HTTPException(
                status_code=503,
                detail="no embedding index — run `python -m eval_harness.run` once to build it",
            )
        _BASELINE_INDEX = json.loads(_BASELINE_PATH.read_text())

    try:
        started = time.perf_counter()
        files = embed_retrieve(_BASELINE_INDEX, request.question, request.k)
        return {
            "question": request.question,
            "files": files,
            "trust": {
                "ms": round((time.perf_counter() - started) * 1000),
                "corpus_files": len(_BASELINE_INDEX),
                "engine": f"cosine similarity over {os.environ.get('NVIDIA_EMBED_MODEL', 'nvidia/llama-nemotron-embed-1b-v2')}",
                "top_k": request.k,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — needs an API key; say so plainly
        raise HTTPException(status_code=503, detail=f"baseline unavailable: {exc}") from exc


@app.get("/api/evidence")
def evidence(
    symbol_id: int, from_id: int | None = None, max_len: int = 5, path_count: int = 12
) -> dict:
    """Why a row is in the blast radius.

    With `from_id` (the changed symbol) this returns the chains that connect the
    change to this row — the question a reviewer is actually asking. Without it,
    it returns what the symbol reaches on its own.
    """
    c = client()
    try:
        started = time.perf_counter()
        if from_id is not None:
            paths, complete = paths_between(
                c, from_id, symbol_id, max_len=max_len, path_count=path_count
            )
        else:
            paths, complete = evidence_paths(
                c, symbol_id, max_len=min(max_len, 4), path_count=path_count
            )
        return {
            "paths": paths,
            "trust": {
                "complete": complete,
                "sampled": not complete,
                "max_len": max_len,
                "path_count": path_count,
                "ms": round((time.perf_counter() - started) * 1000),
                "engine": "HydraDB native path procedure (algo.SPpaths / algo.SSpaths)",
            },
        }
    finally:
        c.close()


WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")
