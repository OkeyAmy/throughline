# Evaluation — graph traversal vs embedding retrieval

Both methods answer the same question (*which files reference this symbol?*)
and return the same number of files (**k = 25**): the graph ranked by hop
distance, the baseline by cosine similarity. Ground truth is ripgrep over the
checked-out source, produced by neither method.

- sample: **20 symbols** from starlette, httpcore, uvicorn, seed 7
- sampling rule: per letter A-Z: up to 40 prefix matches, keep non-test .py definitions in the target repos, shuffle with the given seed, take those with >= 2 referencing files
- corpus: 828 Python files across the 5 repos (`docs_src/` excluded from both sides)
- graph rows limited to 3 hops; baseline is `nvidia/llama-nemotron-embed-1b-v2`

## Headline: references in another repository

The case this architecture exists for. A package boundary is a structural fact,
not a lexical one.

| method | cross-repo recall |
|---|---|
| graph, "other repos" filter (what the product does) | **0.506** |
| embedding baseline | **0.453** |
| graph, default ranking (nearest hop first) | **0.100** |

Measured on the 10 sampled symbols referenced outside their own repo. The third row is the honest failure mode: cross-repo hits sit at hop 3 or deeper, so a flat top-k ranked by hop distance fills up with same-repo rows before reaching them. The filter exists in the UI for exactly this reason.

## Overall, at matched k

| method | precision | recall | F1 | median ms |
|---|---|---|---|---|
| graph | 0.261 | 0.679 | 0.350 | 387 |
| baseline | 0.156 | 0.587 | 0.226 | 1592 |

Graph F1 beat the baseline on **13 of 20** symbols.

## Per symbol

| symbol | repo | truth | cross-repo truth | graph P/R/F1 | baseline P/R/F1 | closure |
|---|---|---|---|---|---|---|
| `Lock` | httpcore | 7 | 2 | 0.26/0.71/0.38 | 0.08/0.29/0.12 | exact |
| `Jinja2Templates` | starlette | 2 | 1 | 0.67/1.00/0.80 | 0.08/1.00/0.15 | exact |
| `HTTPScope` | uvicorn | 6 | 0 | 0.24/1.00/0.39 | 0.16/0.67/0.26 | exact |
| `H11Protocol` | uvicorn | 11 | 0 | 0.36/0.82/0.50 | 0.28/0.64/0.39 | exact |
| `HTTPConnection` | starlette | 15 | 10 | 0.20/0.33/0.25 | 0.16/0.27/0.20 | exact |
| `NetworkStream` | httpcore | 10 | 0 | 0.38/0.90/0.53 | 0.24/0.60/0.34 | exact |
| `LifespanOn` | uvicorn | 3 | 0 | 0.50/0.67/0.57 | 0.08/0.67/0.14 | exact |
| `ZttpProtocol` | uvicorn | 3 | 0 | 0.04/0.33/0.07 | 0.08/0.67/0.14 | exact |
| `Match` | starlette | 4 | 4 | 0.00/0.00/0.00 | 0.08/0.50/0.14 | exact |
| `Middleware` | starlette | 21 | 4 | 0.68/0.81/0.74 | 0.28/0.33/0.30 | exact |
| `WebSocketRoute` | starlette | 7 | 1 | 0.24/0.86/0.38 | 0.16/0.57/0.25 | exact |
| `HttpToolsProtocol` | uvicorn | 10 | 0 | 0.32/0.80/0.46 | 0.24/0.60/0.34 | exact |
| `WebSocketDenialResponse` | starlette | 2 | 0 | 0.08/1.00/0.15 | 0.08/1.00/0.15 | exact |
| `HTTPRequestEvent` | uvicorn | 5 | 0 | 0.20/1.00/0.33 | 0.16/0.80/0.27 | exact |
| `QueryParams` | starlette | 12 | 10 | 0.08/0.17/0.11 | 0.12/0.25/0.16 | exact |
| `Mount` | starlette | 11 | 2 | 0.36/0.82/0.50 | 0.20/0.45/0.28 | exact |
| `HTMLResponse` | starlette | 8 | 6 | 0.08/0.25/0.12 | 0.20/0.62/0.30 | partial |
| `WebSocketConnectEvent` | uvicorn | 2 | 0 | 0.08/1.00/0.15 | 0.08/1.00/0.15 | exact |
| `Host` | starlette | 38 | 32 | 0.16/0.11/0.13 | 0.16/0.11/0.13 | exact |
| `NetworkBackend` | httpcore | 7 | 0 | 0.29/1.00/0.45 | 0.20/0.71/0.31 | exact |

## Reading these numbers honestly

- **The truth set is lexical.** Ripgrep counts any word-boundary mention, including
  comments and same-named locals. That favours the embedding baseline, whose query
  contains the symbol name — and it still caps precision for both methods.
- **Matched k understates the graph's reach.** The closure typically returns hundreds
  of nodes; only its nearest k are scored here, because scoring 748 against 25 would
  not be a comparison. The full closure is what the product returns.
- **Symbols with fewer than two referencing files were skipped**, not scored — a
  symbol nothing references is not a win for anyone.
- The graph is expected to lose where lexical matching is enough. Where it wins is
  where structure is the only signal: another repository, a transitive caller, a test
  that never names the symbol it exercises.

Raw per-symbol data: `eval_harness/results.json`. Re-run: `python -m eval_harness.run`.
