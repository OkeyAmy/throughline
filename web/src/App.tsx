import { useCallback, useEffect, useRef, useState } from "react";
import {
  type EvidencePath,
  type ImpactRow,
  type Level,
  type Symbol,
  type Totals,
  type Trust,
  evidence,
  health,
  searchSymbols,
  streamImpact,
} from "./api";
import { EvidencePanel } from "./components/EvidencePanel";
import { ImpactList } from "./components/ImpactList";
import { TrustStrip } from "./components/TrustStrip";

export default function App() {
  const [query, setQuery] = useState("JSONResponse");
  const [matches, setMatches] = useState<Symbol[]>([]);
  const [seed, setSeed] = useState<Symbol | null>(null);
  const [levels, setLevels] = useState<Level[]>([]);
  const [rows, setRows] = useState<ImpactRow[]>([]);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [trust, setTrust] = useState<Trust | null>(null);
  const [walking, setWalking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "cross" | "tests">("all");
  const [selected, setSelected] = useState<number | null>(null);
  const [paths, setPaths] = useState<EvidencePath[]>([]);
  const [pathsComplete, setPathsComplete] = useState(true);
  const [pathsMs, setPathsMs] = useState(0);
  const [pathsLoading, setPathsLoading] = useState(false);
  const [graphNodes, setGraphNodes] = useState<number | null>(null);
  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    health()
      .then((h) => setGraphNodes(h.nodes))
      .catch(() => setError("HydraDB is not answering — is the node running?"));
  }, []);

  useEffect(() => {
    if (query.trim().length < 2) {
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
  }, [query]);

  const walk = useCallback((symbol: Symbol) => {
    stopRef.current?.();
    setSeed(symbol);
    setMatches([]);
    setQuery(symbol.name);
    setLevels([]);
    setRows([]);
    setTotals(null);
    setTrust(null);
    setSelected(null);
    setPaths([]);
    setError(null);
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

  const showEvidence = useCallback((row: ImpactRow) => {
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
  }, [seed]);

  const repoEntries = Object.entries(totals?.repos ?? {}).sort((a, b) => b[1] - a[1]);
  const widest = repoEntries[0]?.[1] ?? 1;

  return (
    <div className="flex h-full flex-col" style={{ background: "var(--surface)" }}>
      <header
        className="flex flex-wrap items-baseline justify-between gap-3 border-b px-6 py-4"
        style={{ borderColor: "var(--rule)" }}
      >
        <div className="flex items-baseline gap-4">
          <h1 className="display text-[26px] leading-none">throughline</h1>
          <p className="text-[11px]" style={{ color: "var(--ink-dim)" }}>
            what a change reaches — across every repo in the workspace
          </p>
        </div>
        <p className="text-[11px]" style={{ color: "var(--ink-faint)" }}>
          {graphNodes ? `${graphNodes.toLocaleString()} symbols in HydraDB` : "connecting…"}
        </p>
      </header>

      <section className="border-b px-6 py-4" style={{ borderColor: "var(--rule)" }}>
        <span className="section-marker">01 / what are you changing</span>
        <div className="mt-2 flex items-center gap-3">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && matches.length > 0) walk(matches[0]);
            }}
            placeholder="a function, class or module…"
            spellCheck={false}
            className="w-full max-w-md border bg-transparent px-3 py-2 outline-none"
            style={{ borderColor: "var(--rule)", color: "var(--ink)" }}
          />
          <button
            onClick={() => matches.length > 0 && walk(matches[0])}
            disabled={matches.length === 0 || walking}
            className="border px-3 py-2 text-[12px] disabled:opacity-40"
            style={{ borderColor: "var(--ink)", color: "var(--ink)" }}
          >
            {walking ? "walking…" : "trace impact"}
          </button>
        </div>

        {matches.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-2">
            {matches.slice(0, 6).map((match) => (
              <li key={match.id}>
                <button
                  onClick={() => walk(match)}
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
            <span style={{ color: "var(--ink)" }}>{seed.name}</span> · {seed.repo} ·{" "}
            {seed.path}
            {seed.line > 0 ? `:${seed.line}` : ""}
          </p>
        )}

        {/* The walk, hop by hop. Each tick is a level HydraDB has finished serving. */}
        {(walking || levels.length > 0) && (
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
              <span style={{ color: "var(--ink-dim)" }}>outside {seed?.repo}</span>
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

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
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

      <TrustStrip trust={trust} nodes={graphNodes} />
    </div>
  );
}
