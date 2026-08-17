import type { ImpactRow } from "../api";

/**
 * The comparison, live: the same question answered by embedding similarity,
 * asked for exactly as many files as the walk found — so the two are matched
 * at k and one overlap number means something. The walk is the reference set
 * here, not independent ground truth; that comparison is in the README.
 */
export function BaselineSplit({
  files,
  rows,
  ms,
  corpus,
  engine,
  loading,
  error,
}: {
  files: string[];
  rows: ImpactRow[];
  ms: number;
  corpus: number;
  engine: string;
  loading: boolean;
  error: string | null;
}) {
  const reachedFiles = new Set(rows.map((row) => row.path));
  const totalFiles = reachedFiles.size;
  const sharedFiles = new Set(files.filter((file) => reachedFiles.has(file)));
  const shared = sharedFiles.size;
  const pct = totalFiles > 0 ? Math.round((shared / totalFiles) * 100) : 0;

  return (
    <section
      className="border-t px-6 py-4 lg:max-h-[38vh] lg:shrink-0 lg:overflow-y-auto"
      style={{ borderColor: "var(--rule)" }}
    >
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="section-marker">04 / same question, by similarity</span>
        <span className="text-[11px]" style={{ color: "var(--ink-faint)" }}>
          {loading
            ? "embedding…"
            : error
              ? error
              : `top ${files.length} of ${corpus} files · ${ms} ms · ${engine}`}
        </span>
      </div>

      {!loading && !error && files.length > 0 && (
        <>
          <div className="mt-3 flex max-w-2xl items-center gap-3">
            <div className="h-4 min-w-8 flex-1" style={{ background: "var(--surface-2)" }}>
              <div
                className="h-4"
                style={{ width: `${Math.max(pct, shared > 0 ? 2 : 0)}%`, background: "var(--series-call)" }}
              />
            </div>
            <span
              className="w-32 shrink-0 text-right text-[11px] tabular-nums"
              style={{ color: "var(--ink)" }}
            >
              {shared} of {totalFiles} ({pct}%)
            </span>
          </div>
          <p className="mt-1 max-w-2xl text-[11px]" style={{ color: "var(--ink-faint)" }}>
            files the similarity search also found, asked for the same count ({files.length}) the
            walk returned
          </p>
          <p className="mt-2 max-w-2xl text-[11px]" style={{ color: "var(--ink-dim)" }}>
            The walk's {totalFiles} files are the reference set here, not independent ground
            truth — the ripgrep-verified eval (F1 0.350 graph vs 0.226 similarity, n=60) is in the
            README.
          </p>
          <details className="mt-2">
            <summary className="cursor-pointer text-[11px]" style={{ color: "var(--ink-faint)" }}>
              show the {files.length} files
            </summary>
            <ul className="mt-2 grid gap-x-6 gap-y-1 md:grid-cols-2">
              {files.map((file) => {
                const alsoInGraph = reachedFiles.has(file);
                return (
                  <li key={file} className="flex items-baseline gap-2 text-[11px]">
                    <span
                      aria-hidden
                      className="inline-block h-[6px] w-[6px] shrink-0 rounded-full"
                      style={{
                        background: alsoInGraph ? "var(--series-call)" : "var(--rule)",
                      }}
                    />
                    <span
                      className="truncate"
                      style={{ color: alsoInGraph ? "var(--ink)" : "var(--ink-faint)" }}
                      title={alsoInGraph ? "also found by the walk" : "similarity only"}
                    >
                      {file}
                    </span>
                    <span className="shrink-0 text-[10px]" style={{ color: "var(--ink-faint)" }}>
                      {alsoInGraph ? "both" : "similarity only"}
                    </span>
                  </li>
                );
              })}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
