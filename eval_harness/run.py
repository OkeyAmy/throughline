"""Graph traversal vs embedding retrieval, on ground truth neither one produced.

    python -m eval_harness.run --sample 20

**The question both methods answer:** which files reference this symbol?

**Truth:** ripgrep word-boundary matches over the checked-out source — independent
of our extractor and of the embedding index. It is a lexical signal, which matters
when reading the numbers: a query containing the symbol name gives the embedding
baseline something to latch onto, and neither method can score 1.00 precision
against a truth set that counts comments and same-named locals.

**Budgets are matched.** Both methods return the same number of files (`--k`),
ranked: the graph by hop distance, the baseline by cosine similarity. Comparing a
748-node closure against a top-25 list would not be a comparison.

The headline result is the cross-repo one — files in a *different repository* from
the symbol. That is the case this architecture exists for, and it is fair at any k.
"""

from __future__ import annotations

import argparse
import json
import random
import string
import time
from pathlib import Path

import httpx

from eval_harness.embed_baseline import EXCLUDED_PATH_PARTS, build_index, retrieve
from eval_harness.ground_truth import referencing_files
from eval_harness.metrics import prf

API = "http://127.0.0.1:8000"

#: How symbols are chosen, stated so the sample is a decision rather than an accident:
#: for each letter A-Z, take up to 40 prefix matches from the graph, keep definitions
#: in the requested repos that live in a .py file outside a test directory, then
#: shuffle with a fixed seed and walk the list until `--sample` symbols have enough
#: ground truth to score.
SAMPLE_RULE = (
    "per letter A-Z: up to 40 prefix matches, keep non-test .py definitions in the "
    "target repos, shuffle with the given seed, take those with >= 2 referencing files"
)


def graph_files(symbol_id: int, k: int, max_hop: int) -> tuple[list[str], list[str], dict, int]:
    """The graph's top-k files, nearest hop first — the same budget as the baseline.

    Returns two rankings, because the product offers two: the default (nearest hop
    first) and the "other repos" filter, which is the control a user clicks when the
    question is *what did this change reach outside my repo*. Scoring cross-repo
    recall against the default ranking measures a truncation, not a retrieval.
    """
    response = httpx.post(
        f"{API}/api/impact",
        json={"symbol_id": symbol_id, "limit": 4000, "max_depth": 12},
        timeout=300,
    )
    response.raise_for_status()
    payload = response.json()

    ordered: list[str] = []
    cross_first: list[str] = []
    for row in sorted(payload["rows"], key=lambda r: r["hop"]):
        path = row["path"]
        if not path or row["hop"] > max_hop:
            continue
        if any(part in f"/{path}" for part in EXCLUDED_PATH_PARTS):
            continue
        if path not in ordered:
            ordered.append(path)
        if row["cross_repo"] and path not in cross_first:
            cross_first.append(path)
    return ordered[:k], cross_first[:k], payload["trust"], payload["totals"]["impacted"]


def sample_symbols(count: int, seed: int, repos: list[str]) -> list[dict]:
    rng = random.Random(seed)
    picked: dict[int, dict] = {}
    for letter in string.ascii_uppercase:
        found = httpx.get(
            f"{API}/api/symbols", params={"q": letter, "limit": 40}, timeout=60
        ).json()["symbols"]
        for symbol in found:
            if (
                symbol["repo"] in repos
                and symbol["path"].endswith(".py")
                and "/tests/" not in symbol["path"]
                and not symbol["path"].split("/")[-1].startswith("test_")
            ):
                picked[symbol["id"]] = symbol
    ordered = sorted(picked.values(), key=lambda s: s["id"])
    rng.shuffle(ordered)
    return ordered[:count]


def main() -> None:
    parser = argparse.ArgumentParser(description="graph vs embeddings on ripgrep truth")
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-hop", type=int, default=3)
    parser.add_argument("--k", type=int, default=25, help="files returned by BOTH methods")
    parser.add_argument("--repos", nargs="*", default=["starlette", "httpcore", "uvicorn"])
    parser.add_argument("--checkouts", default=".repos")
    parser.add_argument("--out", default="eval_harness/results.md")
    args = parser.parse_args()

    roots = [
        Path(args.checkouts) / name
        for name in ("fastapi", "starlette", "uvicorn", "httpx", "httpcore")
    ]
    missing = [str(r) for r in roots if not r.exists()]
    if missing:
        raise SystemExit(f"missing checkouts: {missing} — run scripts/fetch_workspace.sh first")

    print("loading embedding index (built once, cached)…")
    index = build_index(roots, cache=Path("eval_harness/.embed-index.json"))
    print(f"  {len(index)} files in the corpus")

    results = []
    for symbol in sample_symbols(args.sample * 6, args.seed, args.repos):
        if len(results) >= args.sample:
            break
        name = symbol["name"].strip("()")
        truth = referencing_files(name, roots, exclude_path=symbol["path"])
        if len(truth) < 2:
            continue  # unanswerable: skipped, not scored as a win for either side

        started = time.perf_counter()
        graph, graph_cross_ranked, trust, impacted = graph_files(
            symbol["id"], args.k, args.max_hop
        )
        graph_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        question = f"which files use {symbol['name']} from {symbol['path']}?"
        baseline = retrieve(index, question, args.k)
        baseline_ms = (time.perf_counter() - started) * 1000

        cross_truth = {p for p in truth if not p.startswith(f"{symbol['repo']}/")}
        results.append(
            {
                "symbol": symbol["name"],
                "repo": symbol["repo"],
                "path": symbol["path"],
                "truth": len(truth),
                "cross_repo_truth": len(cross_truth),
                "impacted_total": impacted,
                "graph": prf(set(graph), truth),
                "baseline": prf(set(baseline), truth),
                "graph_cross": prf(set(graph) & cross_truth, cross_truth) if cross_truth else None,
                "graph_cross_filtered": prf(set(graph_cross_ranked), cross_truth)
                if cross_truth
                else None,
                "baseline_cross": prf(set(baseline) & cross_truth, cross_truth)
                if cross_truth
                else None,
                "graph_ms": round(graph_ms),
                "baseline_ms": round(baseline_ms),
                "exact": trust["exact"],
            }
        )
        last = results[-1]
        print(
            f"  {symbol['name'][:26]:28} truth={len(truth):3} cross={len(cross_truth):3}  "
            f"graph F1={last['graph'][2]:.2f}  baseline F1={last['baseline'][2]:.2f}"
        )

    write_report(results, args, corpus=len(index))


def write_report(results: list[dict], args, corpus: int) -> None:
    def mean(method: str, position: int) -> float:
        values = [r[method][position] for r in results if r[method]]
        return sum(values) / len(values) if values else 0.0

    cross = [r for r in results if r["graph_cross"]]
    wins = sum(1 for r in results if r["graph"][2] > r["baseline"][2])

    lines = [
        "# Evaluation — graph traversal vs embedding retrieval",
        "",
        "Both methods answer the same question (*which files reference this symbol?*)",
        f"and return the same number of files (**k = {args.k}**): the graph ranked by hop",
        "distance, the baseline by cosine similarity. Ground truth is ripgrep over the",
        "checked-out source, produced by neither method.",
        "",
        f"- sample: **{len(results)} symbols** from {', '.join(args.repos)}, seed {args.seed}",
        f"- sampling rule: {SAMPLE_RULE}",
        f"- corpus: {corpus} Python files across the 5 repos (`docs_src/` excluded from both sides)",
        f"- graph rows limited to {args.max_hop} hops; baseline is `nvidia/llama-nemotron-embed-1b-v2`",
        "",
        "## Headline: references in another repository",
        "",
        "The case this architecture exists for. A package boundary is a structural fact,",
        "not a lexical one.",
        "",
        "| method | cross-repo recall |",
        "|---|---|",
    ]
    if cross:
        labels = {
            "graph_cross_filtered": "graph, \"other repos\" filter (what the product does)",
            "baseline_cross": "embedding baseline",
            "graph_cross": "graph, default ranking (nearest hop first)",
        }
        for method in ("graph_cross_filtered", "baseline_cross", "graph_cross"):
            values = [r[method][1] for r in cross if r[method]]
            lines.append(
                f"| {labels[method]} | **{sum(values) / len(values):.3f}** |"
            )
        lines.append("")
        lines.append(
            f"Measured on the {len(cross)} sampled symbols referenced outside their own repo. "
            "The third row is the honest failure mode: cross-repo hits sit at hop 3 or "
            "deeper, so a flat top-k ranked by hop distance fills up with same-repo rows "
            "before reaching them. The filter exists in the UI for exactly this reason."
        )
    else:
        lines.append("| — | no sampled symbol had references outside its own repo |")

    lines += [
        "",
        "## Overall, at matched k",
        "",
        "| method | precision | recall | F1 | median ms |",
        "|---|---|---|---|---|",
    ]
    for method in ("graph", "baseline"):
        times = sorted(r[f"{method}_ms"] for r in results)
        median = times[len(times) // 2] if times else 0
        lines.append(
            f"| {method} | {mean(method, 0):.3f} | {mean(method, 1):.3f} | "
            f"{mean(method, 2):.3f} | {median} |"
        )
    lines += [
        "",
        f"Graph F1 beat the baseline on **{wins} of {len(results)}** symbols.",
        "",
        "## Per symbol",
        "",
        "| symbol | repo | truth | cross-repo truth | graph P/R/F1 | baseline P/R/F1 | closure |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        g, b = r["graph"], r["baseline"]
        lines.append(
            f"| `{r['symbol']}` | {r['repo']} | {r['truth']} | {r['cross_repo_truth']} | "
            f"{g[0]:.2f}/{g[1]:.2f}/{g[2]:.2f} | {b[0]:.2f}/{b[1]:.2f}/{b[2]:.2f} | "
            f"{'exact' if r['exact'] else 'partial'} |"
        )

    lines += [
        "",
        "## Reading these numbers honestly",
        "",
        "- **The truth set is lexical.** Ripgrep counts any word-boundary mention, including",
        "  comments and same-named locals. That favours the embedding baseline, whose query",
        "  contains the symbol name — and it still caps precision for both methods.",
        "- **Matched k understates the graph's reach.** The closure typically returns hundreds",
        "  of nodes; only its nearest k are scored here, because scoring 748 against 25 would",
        "  not be a comparison. The full closure is what the product returns.",
        "- **Symbols with fewer than two referencing files were skipped**, not scored — a",
        "  symbol nothing references is not a win for anyone.",
        "- The graph is expected to lose where lexical matching is enough. Where it wins is",
        "  where structure is the only signal: another repository, a transitive caller, a test",
        "  that never names the symbol it exercises.",
        "",
        "Raw per-symbol data: `eval_harness/results.json`. Re-run: `python -m eval_harness.run`.",
    ]

    Path(args.out).write_text("\n".join(lines) + "\n")
    Path("eval_harness/results.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
