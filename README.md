# throughline

**What a change reaches — across every repo in the workspace.**

Ask what breaks if you change `JSONResponse`, and throughline answers by walking a
code graph in [HydraDB](https://github.com/hydra-db/hydradb): 748 symbols reached,
**567 of them in a different repository**, 590 tests to run, in about a second —
with the paths that prove it.

Built for [Hack Hydra](https://hackhydra.hydradb.com/) 2026, **Track 02B — code
graphs for IDE assistants**.

---

## The problem

A coding agent's blind spot is not *what does this code say*, it is **what does
this change touch**. Ask one to change a function signature and it edits the
definition and the two call sites it happened to retrieve. The rest of the blast
radius — transitive callers, the tests that cover them, the other service that
imports the published package — is invisible, because retrieval is similarity over
chunks and structure is not similar to anything.

Structure-aware tooling exists, but it is local and single-repo: graphify's
`affected` walks an in-memory `graph.json` on one machine, one repository at a
time. Nothing serves that structure as a shared, durable, queryable service.

That is the gap an object-store-native graph database fills, and it is what this is.

---

## What HydraDB does here

HydraDB is not a store this project writes to and forgets. It **executes the
product**:

| Job | How |
|---|---|
| Holds the organisation's code graph | 33,995 symbols, 111,382 edges across 5 repos, durable on object storage, shared by every client |
| Answers *what does this change reach* | Batched BFS: one round trip per (hop × edge type), whole frontier passed as an `UNWIND` batch — HydraDB walks the adjacency, the client only carries ids |
| Answers *why is this reached* | `algo.SPpaths` / `algo.SSpaths` with a **list** of relationship types — heterogeneous multi-hop in one call |
| Joins repos | A `PROVIDES` edge from an external package node to the repo that defines it — the traversal crosses repository boundaries without leaving the database |

**What this project would lose without HydraDB:** the graph stops being shared and
durable. Every agent would need the whole graph in its own memory, per repo, rebuilt
per run, with no cross-repo joins, no snapshot-consistent reads while the graph is
being updated, and no server-side path procedures. The traversal *is* the product.

There are no embeddings in the answer path. Retrieval is traversal.

---

## Quickstart

Needs Docker, Python 3.11+, Node 20+ (only to rebuild the UI), and
[uv](https://docs.astral.sh/uv/) or pip.

```bash
# 1. HydraDB
docker compose up -d hydradb

# 2. build the demo workspace: clone 5 public repos, extract code graphs
uv tool install graphifyy          # the extractor (Apache-2.0, see Attribution)
./scripts/fetch_workspace.sh

# 3. load the graph into HydraDB (~70 s for 111k edges)
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m loader ingest --workspace workspace.yml

# 4. serve — bind 0.0.0.0, not the uvicorn default. Chrome resolves `localhost`
#    to ::1, where a 127.0.0.1-only bind is not listening: the page loads and
#    every API call fails silently.
.venv/bin/uvicorn server.app:app --host 0.0.0.0 --port 8000
open http://127.0.0.1:8000
```

Whole stack in containers instead (verified end-to-end — HydraDB, ingest, and the
app, from an empty volume):

```bash
docker compose up -d                              # HydraDB + the service
docker compose --profile tools run --rm ingest    # waits for readiness, loads the graph
open http://127.0.0.1:8000
```

`data/` must already contain the extracted graphs (step 2 above); the ingest
container mounts it read-only.

Environment: copy `.env.example` to `.env`. Everything works without an API key
except the plain-English `/api/ask` summary and the evaluation baseline, which use
NVIDIA's OpenAI-compatible endpoint.

---

## Using it

**Web** — search a symbol, watch the walk expand hop by hop, filter to *other
repos* or *tests to run*, click any row for the paths that connect the change to it.

**Agents (MCP)** — six tools over the same query layer:

| Tool | Answers |
|---|---|
| `impact_of_change` | what breaks if this changes, across repos |
| `tests_for` | which tests to run before pushing |
| `callers_of` | who calls this, within N hops |
| `code_context` | graph-grounded context for a plain-English question |
| `why_connected` | the evidence paths out of a symbol |
| `find_symbol` | definitions first, stubs last |

```jsonc
// Claude Code / Cursor / Codex — mcpServers entry
{
  "throughline": {
    "command": "/path/to/throughline/.venv/bin/python",
    "args": ["-m", "mcp_server"],
    "env": { "HYDRADB_URL": "http://127.0.0.1:8443" }
  }
}
```

**HTTP**

```bash
curl -X POST localhost:8000/api/impact -d '{"symbol":"JSONResponse"}' -H 'Content-Type: application/json'
curl -X POST localhost:8000/api/impact/pr -d '{"url":"https://github.com/encode/starlette/pull/3431"}' -H 'Content-Type: application/json'
curl -X POST localhost:8000/api/ask -d '{"question":"what breaks if I change JSONResponse"}' -H 'Content-Type: application/json'
curl -N "localhost:8000/api/impact/stream?symbol_id=26689"    # level-by-level SSE
```

---

## How it is built

```
graphify (tree-sitter, ~40 languages)   →   loader   →   HydraDB   →   server   →   web + MCP
  one graph.json per repo                  ids, batches,   the graph    closure,     4 surfaces,
                                           inverse edges,   itself      evidence,    6 tools
                                           cross-repo joins             ranking
```

- **`loader/`** — parses graphify output, assigns integer node and relationship ids,
  writes 1000-row `UNWIND` batches, and materialises an inverse edge for every
  structural edge.
- **`server/closure.py`** — the answer engine. Level-by-level BFS, edge types within
  a level run concurrently, every result carries `{exact, depth, round_trips, ms}`.
- **`server/hydra.py`** — the only place Cypher is written.
- **`mcp_server/`** — MCP tools, laid out after `hydra-db/hydradb-mcp`.
- **`web/`** — React + Vite + Tailwind; the built bundle is served by FastAPI.

### Why inverse edges

HydraDB rejects a reverse variable-length pattern:

```
MATCH (callee {id:$id})<-[:CALLS*1..3]-(caller)
→ "variable-length MATCH requires a fixed source id"
```

and its batched read form only expands from the pattern *source*. So "who calls X"
is written as a forward walk over a materialised `CALLED_BY` edge. Ingest writes
both directions; the walk is one round trip per hop.

---

## What we measured about HydraDB

Numbers from `ghcr.io/hydra-db/hydradb:latest` on this workspace, not from docs.

| Finding | Measurement |
|---|---|
| **Path procedures are complete up to a depth, then not** | On a 60k-node / 120k-edge graph, `algo.SSpaths` returned **recall 1.000** at maxLen 2/3/4 once `pathCount` exceeded the true path count — but **0.685 at maxLen 5**, returning ~1024 paths even with `pathCount=100000` |
| **Batched BFS over inverse edges is exact** | recall **1.000** at depths 4, 6, 10 and 20; depth 20 over 5,745 nodes = **1.6 s, 20 round trips** |
| **Concurrency across edge types** | 2,678 ms → **460 ms** for the same walk (6 edge types in parallel) |
| **Ingest** | nodes ~60k/s; edges ~2.3k/s single-threaded; **1000 rows is a hard batch cap** (`client_query_batch_items` admission control rejects 2000) |
| **Path result cap** | `resultLimit` above 100000 is rejected by admission control |

The first row matters for anyone building on HydraDB: a prior public write-up
([substrate-friction](https://github.com/areycruzer/substrate-friction)) reported
path procedures returning 2.6% of paths and concluded they were broadly lossy. On
our data most of that gap closes by raising `pathCount` — but a real cap remains at
depth. So this project uses path procedures for **evidence** and never for a set,
and says so in the UI when a result is a sample.

Every answer therefore carries its provenance:

```json
"trust": {
  "exact": true, "depth": 8, "round_trips": 54, "ms": 972,
  "engine": "batched BFS over materialised inverse edges (HydraDB)"
}
```

An impact answer that silently dropped callers is a wrong answer, not an
approximate one.

---

## Evaluation

Graph traversal vs real embedding retrieval (`nvidia/llama-nemotron-embed-1b-v2`),
both returning **the same number of files (k = 25)**, scored against ground truth
neither method produced: ripgrep word-boundary matches over the checked-out source.
20 symbols from starlette, httpcore and uvicorn.

| method | precision | recall | F1 | median ms |
|---|---|---|---|---|
| **graph traversal** | **0.261** | **0.679** | **0.350** | **387** |
| embedding baseline | 0.156 | 0.587 | 0.226 | 1592 |

Graph F1 beat the baseline on 13 of 20 symbols, at a quarter of the latency.

**References in another repository** — the case this architecture exists for, on the
10 sampled symbols that have them:

| method | cross-repo recall |
|---|---|
| graph, "other repos" filter (what the product does) | **0.506** |
| embedding baseline | 0.453 |
| graph, default ranking (nearest hop first) | 0.100 |

That last row is a real failure mode, not a footnote: cross-repo hits sit at hop 3
or deeper, so a flat top-k ranked by hop distance fills with same-repo rows before
reaching them. The UI's cross-repo filter exists because of it, and the margin over
embeddings even with the filter is thin — 0.506 to 0.453.

Method, per-symbol table, and what the numbers do *not* show:
**[eval_harness/results.md](eval_harness/results.md)**. Re-run: `python -m eval_harness.run`.

---

## Limitations

- **Cross-repo links are configured, not inferred.** `workspace.yml` maps each repo
  to the package name it publishes. Import-name to distribution-name resolution
  (`import yaml` → `PyYAML`) is a genuine problem and guessing it wrong produces a
  graph that looks connected and isn't.
- **Cross-repo joins are module-level.** `fastapi` importing `starlette.responses`
  links to that module, and the walk continues inside starlette from there. It does
  not resolve `from starlette.responses import JSONResponse` to the class directly.
- **Extraction inherits graphify's limits** — `INFERRED` edges are resolution, not
  proof, and the UI shows that tag.
- **Adding a repo is a CLI step**, not a runtime one: clone, extract, re-ingest.
- **Deep evidence paths are samples**, flagged in the UI (see above).

---

## Attribution

- **[HydraDB](https://github.com/hydra-db/hydradb)** (AGPL-3.0) — the graph database.
  Run as a separate service over HTTP; no HydraDB code is linked or vendored here.
- **[graphify](https://github.com/Graphify-Labs/graphify)** (Apache-2.0) — tree-sitter
  code-graph extraction across ~40 languages, used as an installed CLI (`graphifyy`
  on PyPI). throughline does not modify or vendor it.
- Demo workspace: [fastapi](https://github.com/fastapi/fastapi),
  [starlette](https://github.com/encode/starlette), [uvicorn](https://github.com/encode/uvicorn),
  [httpx](https://github.com/encode/httpx), [httpcore](https://github.com/encode/httpcore)
  — public repositories, cloned at build time, not redistributed here.
- LLM and embeddings: NVIDIA NIM OpenAI-compatible endpoint.
- Python: FastAPI, httpx, PyYAML, pytest. Web: React, Vite, Tailwind CSS,
  Newsreader and JetBrains Mono (SIL OFL, self-hosted via Fontsource).

Licence: [Apache-2.0](LICENSE).

## Tests

```bash
.venv/bin/python -m pytest        # 91 tests, no network or database required
```
