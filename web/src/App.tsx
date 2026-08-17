import { useCallback, useEffect, useRef, useState } from "react";
import {
  type EvidencePath,
  type ImpactRow,
  type Level,
  type Symbol,
  type Totals,
  type Trust,
  ask,
  baseline,
  evidence,
  health,
  impactOfPr,
  searchSymbols,
  streamImpact,
} from "./api";
import { BaselineSplit } from "./components/BaselineSplit";
import { EvidencePanel } from "./components/EvidencePanel";
import { ImpactList } from "./components/ImpactList";
import { TrustStrip } from "./components/TrustStrip";

type Mode = "symbol" | "pr" | "question";

const MODES: { key: Mode; label: string; placeholder: string }[] = [
  { key: "symbol", label: "a symbol", placeholder: "a function, class or module…" },
  { key: "pr", label: "a pull request", placeholder: "https://github.com/encode/starlette/pull/3431" },
  { key: "question", label: "a question", placeholder: "what breaks if I change JSONResponse?" },
];

export default function App() {
  const [mode, setMode] = useState<Mode>("symbol");
  const [query, setQuery] = useState("JSONResponse");
  const [matches, setMatches] = useState<Symbol[]>([]);
  const [seed, setSeed] = useState<Symbol | null>(null);
  const [levels, setLevels] = useState<Level[]>([]);
  const [rows, setRows] = useState<ImpactRow[]>([]);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [trust, setTrust] = useState<Trust | null>(null);
  const [walking, setWalking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "cross" | "tests">("all");
  const [selected, setSelected] = useState<number | null>(null);
  const [paths, setPaths] = useState<EvidencePath[]>([]);
  const [pathsComplete, setPathsComplete] = useState(true);
  const [pathsMs, setPathsMs] = useState(0);
  const [pathsLoading, setPathsLoading] = useState(false);
  const [graphNodes, setGraphNodes] = useState<number | null>(null);
  const [compare, setCompare] = useState(false);
  const [baselineFiles, setBaselineFiles] = useState<string[]>([]);
  const [baselineMeta, setBaselineMeta] = useState({ ms: 0, corpus: 0, engine: "" });
  const [baselineLoading, setBaselineLoading] = useState(false);
  const [baselineError, setBaselineError] = useState<string | null>(null);
  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    health()
      .then((h) => setGraphNodes(h.nodes))
      .catch(() => setError("HydraDB is not answering — is the node running?"));
  }, []);

  useEffect(() => {
    if (mode !== "symbol" || query.trim().length < 2) {
      setMatches([]);
      return;
    }
    let live = true;
    const timer = setTimeout(() => {
      searchSymbols(query.trim())
        .then((found) => live && setMatches(found))
        .catch(() => live && setMatches([]));
    }, 120);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [query, mode]);

  const reset = () => {
    stopRef.current?.();
    setLevels([]);
    setRows([]);
    setTotals(null);
    setTrust(null);
    setSelected(null);
    setPaths([]);
    setAnswer(null);
    setNote(null);
    setError(null);
    setBaselineFiles([]);
    setBaselineError(null);
  };

  const walkSymbol = useCallback((symbol: Symbol) => {
    reset();
    setSeed(symbol);
    setMatches([]);
    setQuery(symbol.name);
    setWalking(true);
    stopRef.current = streamImpact(symbol.id, {
      onSeed: setSeed,
      onLevel: (level) => setLevels((current) => [...current, level]),
      onDone: (payload) => {
        setRows(payload.rows);
        setTotals(payload.totals);
        setTrust(payload.trust);
        setWalking(false);
      },
      onError: (message) => {
        setError(message);
        setWalking(false);
      },
    });
  }, []);

  const run = useCallback(async () => {
    const text = query.trim();
    if (!text) return;

    if (mode === "symbol") {
      // Prefer a definition in source over a docs mention: `JSONResponse` matches
      // both starlette/responses.py and starlette/docs/responses.md, and walking
      // from the documentation page reaches three nodes instead of 748.
      const best =
        matches.find((m) => m.repo && /\.(py|ts|tsx|js|jsx|rs|go|java|rb)$/.test(m.path)) ??
        matches[0];
      if (best) walkSymbol(best);
      return;
    }

    reset();
    setWalking(true);
    try {
      if (mode === "pr") {
        const result = await impactOfPr(text);
        setSeed(result.seeds?.[0] ?? null);
        setRows(result.rows);
        setTotals(result.totals);
        setTrust((result.trust as Trust) ?? null);
        setNote(
          result.note ??
            `${result.changed_symbols.length} definitions changed in ${result.pr.owner}/${result.pr.repo}#${result.pr.number} · ${result.trust?.seeds ?? 0} matched in the graph`,
        );
      } else {
        const result = await ask(text);
        setSeed(result.seed);
        setRows(result.rows);
        setTotals(result.totals);
        setTrust(result.trust);
        setAnswer(result.answer);
      }
    } catch (exc) {
      setError(String(exc instanceof Error ? exc.message : exc));
    } finally {
      setWalking(false);
    }
  }, [mode, query, matches, walkSymbol]);

  const showEvidence = useCallback(
    (row: ImpactRow) => {
      setSelected(row.id);
      setPathsLoading(true);
      evidence(row.id, seed?.id)
        .then((result) => {
          setPaths(result.paths);
          setPathsComplete(result.trust.complete);
          setPathsMs(result.trust.ms);
        })
        .catch(() => setPaths([]))
        .finally(() => setPathsLoading(false));
    },
    [seed],
  );

  const runBaseline = useCallback(async () => {
    if (!seed) return;
    setCompare(true);
    setBaselineLoading(true);
    setBaselineError(null);
    try {
      const question =
        mode === "question" ? query : `which files use ${seed.name} from ${seed.path}?`;
      const k = new Set(rows.map((row) => row.path)).size || 15;
      const result = await baseline(question, k);
      setBaselineFiles(result.files);
      setBaselineMeta({
        ms: result.trust.ms,
        corpus: result.trust.corpus_files,
        engine: result.trust.engine,
      });
    } catch (exc) {
      setBaselineError(String(exc instanceof Error ? exc.message : exc));
    } finally {
      setBaselineLoading(false);
    }
  }, [seed, mode, query, rows]);

  const repoEntries = Object.entries(totals?.repos ?? {}).sort((a, b) => b[1] - a[1]);
  const widest = repoEntries[0]?.[1] ?? 1;
  const placeholder = MODES.find((m) => m.key === mode)!.placeholder;

  return (
    <div className="flex min-h-full flex-col lg:h-full" style={{ background: "var(--surface)" }}>
      <header
        className="flex flex-wrap items-baseline justify-between gap-3 border-b px-6 py-4"
        style={{ borderColor: "var(--rule)" }}
      >
        <div className="flex items-baseline gap-4">
          <h1 className="display text-[26px] leading-none">throughline</h1>
          <p className="text-[11px]" style={{ color: "var(--ink-dim)" }}>
            you changed a function — what else breaks, including in repos you don't have open?
          </p>
        </div>
        <p className="text-[11px]" style={{ color: "var(--ink-faint)" }}>
          {graphNodes ? `${graphNodes.toLocaleString()} symbols in HydraDB` : "connecting…"}
        </p>
      </header>

      <section className="border-b px-6 py-4" style={{ borderColor: "var(--rule)" }}>
        <div className="flex flex-wrap items-baseline gap-3">
          <span className="section-marker">01 / what are you changing</span>
          <div className="flex gap-1">
            {MODES.map((option) => (
              <button
                key={option.key}
                onClick={() => {
                  setMode(option.key);
                  setQuery("");
                }}
                className="border px-2 py-[3px] text-[11px]"
                style={{
                  borderColor: mode === option.key ? "var(--ink)" : "var(--rule)",
                  color: mode === option.key ? "var(--ink)" : "var(--ink-dim)",
                  background: mode === option.key ? "var(--surface-2)" : "transparent",
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-3">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && run()}
            placeholder={placeholder}
            spellCheck={false}
            className="w-full max-w-2xl border bg-transparent px-3 py-2 outline-none"
            style={{ borderColor: "var(--rule)", color: "var(--ink)" }}
          />
          <button
            onClick={run}
            disabled={walking || !query.trim()}
            className="border px-3 py-2 text-[12px] disabled:opacity-40"
            style={{ borderColor: "var(--ink)", color: "var(--ink)" }}
          >
            {walking ? "walking…" : "trace impact"}
          </button>
          {seed && !walking && (
            <button
              onClick={() => (compare ? setCompare(false) : runBaseline())}
              className="border px-3 py-2 text-[12px]"
              style={{ borderColor: "var(--rule)", color: "var(--ink-dim)" }}
              title="answer the same question by embedding similarity, for comparison"
            >
              {compare ? "back to walk stats" : "compare with embeddings"}
            </button>
          )}
        </div>

        {mode === "symbol" && matches.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-2">
            {matches.slice(0, 6).map((match) => (
              <li key={match.id}>
                <button
                  onClick={() => walkSymbol(match)}
                  className="border px-2 py-1 text-[11px]"
                  style={{ borderColor: "var(--rule)", color: "var(--ink-dim)" }}
                  title={`${match.path}:${match.line}`}
                >
                  {match.name}
                  <span style={{ color: "var(--ink-faint)" }}> · {match.repo || "external"}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {seed && (
          <p className="mt-3 text-[11px]" style={{ color: "var(--ink-dim)" }}>
            <span style={{ color: "var(--ink)" }}>{seed.name}</span> · {seed.repo} · {seed.path}
            {seed.line > 0 ? `:${seed.line}` : ""}
          </p>
        )}

        {note && (
          <p className="mt-2 text-[11px]" style={{ color: "var(--ink-faint)" }}>
            {note}
          </p>
        )}

        {answer && (
          <p
            className="display mt-3 max-w-3xl text-[15px] leading-relaxed"
            style={{ color: "var(--ink)" }}
          >
            {answer}
            <span className="ml-2 text-[10px]" style={{ color: "var(--ink-faint)" }}>
              — written from the rows below; the walk decided them, not the model
            </span>
          </p>
        )}

        {/* Live progress while the walk is running — the hop breakdown below replaces this once it's done. */}
        {walking && levels.length > 0 && (
          <div className="mt-3 flex flex-wrap items-end gap-2">
            {levels.map((level) => (
              <div
                key={level.depth}
                className="level-land border px-2 py-1 text-[11px]"
                style={{ borderColor: "var(--rule)", color: "var(--ink-dim)" }}
                title={`${level.frontier} nodes expanded, ${level.round_trips} round trips so far`}
              >
                <span style={{ color: "var(--ink-faint)" }}>hop {level.depth}</span>{" "}
                <span style={{ color: "var(--ink)" }}>+{level.discovered}</span>{" "}
                <span style={{ color: "var(--ink-faint)" }}>= {level.total}</span>
              </div>
            ))}
            {walking && (
              <span className="text-[11px]" style={{ color: "var(--ink-faint)" }}>
                expanding…
              </span>
            )}
          </div>
        )}

        {error && (
          <p className="mt-3 text-[11px]" style={{ color: "var(--series-cross)" }}>
            {error}
          </p>
        )}

        {totals && (
          <div className="mt-4 flex flex-wrap gap-6">
            <p className="text-[12px]">
              <span className="display text-[20px]">{totals.impacted}</span>{" "}
              <span style={{ color: "var(--ink-dim)" }}>symbols reached</span>
            </p>
            <p className="text-[12px]">
              <span className="display text-[20px]" style={{ color: "var(--series-cross)" }}>
                {totals.cross_repo}
              </span>{" "}
              <span style={{ color: "var(--ink-dim)" }}>outside {seed?.repo ?? "this repo"}</span>
            </p>
            <p className="text-[12px]">
              <span className="display text-[20px]">{totals.tests}</span>{" "}
              <span style={{ color: "var(--ink-dim)" }}>tests to run</span>
            </p>
            <div className="flex min-w-[220px] flex-1 flex-col justify-center gap-1">
              {repoEntries.map(([repo, count]) => (
                <div key={repo} className="flex items-center gap-2 text-[11px]">
                  <span className="w-20 shrink-0 truncate" style={{ color: "var(--ink-dim)" }}>
                    {repo}
                  </span>
                  <span
                    aria-hidden
                    className="h-[6px] rounded-[2px]"
                    style={{
                      width: `${Math.max(4, (count / widest) * 160)}px`,
                      background:
                        repo === seed?.repo ? "var(--series-call)" : "var(--series-cross)",
                    }}
                  />
                  <span className="tabular-nums" style={{ color: "var(--ink-faint)" }}>
                    {count}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      <div className="flex flex-col lg:min-h-0 lg:flex-1 lg:flex-row">
        <ImpactList
          rows={rows}
          seedRepo={seed?.repo ?? ""}
          filter={filter}
          onFilter={setFilter}
          selected={selected}
          onSelect={showEvidence}
        />
        {selected !== null && (
          <EvidencePanel
            paths={paths}
            complete={pathsComplete}
            ms={pathsMs}
            seedName={rows.find((row) => row.id === selected)?.name ?? ""}
            loading={pathsLoading}
          />
        )}
      </div>

      {compare ? (
        <BaselineSplit
          files={baselineFiles}
          rows={rows}
          corpus={baselineMeta.corpus}
          engine={baselineMeta.engine}
          loading={baselineLoading}
          error={baselineError}
        />
      ) : (
        <TrustStrip trust={trust} nodes={graphNodes} />
      )}
    </div>
  );
}
