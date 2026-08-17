import type { ImpactRow } from "../api";

/**
 * The comparison, live: the same question answered by embedding similarity over
 * the same corpus.
 *
 * The bar lengths are the comparison — read at a glance, not computed from
 * prose. Full measured F1 numbers live in eval_harness/results.md, not here.
 */
function BarRow({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}) {
  const pct = max > 0 ? Math.max((value / max) * 100, value > 0 ? 2 : 0) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="w-20 shrink-0 text-[11px]" style={{ color: "var(--ink-dim)" }}>
        {label}
      </span>
      <div className="h-4 flex-1" style={{ background: "var(--surface-2)" }}>
        <div className="h-4" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span
        className="w-20 shrink-0 text-right text-[11px] tabular-nums"
        style={{ color: "var(--ink)" }}
      >
        {value} files
      </span>
    </div>
  );
}

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
  const sharedFiles = new Set(files.filter((file) => reachedFiles.has(file)));
  const shared = sharedFiles.size;
  const beyondFiles = new Set(
    rows.filter((row) => !sharedFiles.has(row.path)).map((row) => row.path),
  );
  const beyond = beyondFiles.size;
  const beyondCrossRepo = new Set(
    rows.filter((row) => row.cross_repo && !sharedFiles.has(row.path)).map((row) => row.path),
  ).size;
  const totalFiles = shared + beyond;
  const scale = Math.max(totalFiles, files.length) || 1;

  return (
    <section className="border-t px-6 py-4" style={{ borderColor: "var(--rule)" }}>
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="section-marker">04 / same question, answered a different way</span>
        <span className="text-[11px]" style={{ color: "var(--ink-faint)" }}>
          {loading
            ? "embedding…"
            : error
              ? error
              : `top ${files.length} of ${corpus} files by similarity · ${ms} ms · ${engine}`}
        </span>
      </div>

      {!loading && !error && files.length > 0 && (
        <>
          <div className="mt-3 flex max-w-2xl flex-col gap-1.5">
            <BarRow label="graph walk" value={totalFiles} max={scale} color="var(--ink)" />
            <BarRow label="similarity" value={files.length} max={scale} color="var(--series-cross)" />
          </div>
          <p className="mt-2 max-w-2xl text-[11px]" style={{ color: "var(--ink-dim)" }}>
            Both found the same <span style={{ color: "var(--series-call)" }}>{shared}</span>. The
            walk found <span style={{ color: "var(--ink)" }}>{beyond}</span> more
            {beyondCrossRepo > 0 && (
              <>
                {" "}
                — <span style={{ color: "var(--series-cross)" }}>{beyondCrossRepo}</span> of them
                in another repository
              </>
            )}
            .
          </p>
          <details className="mt-2">
            <summary
              className="cursor-pointer text-[11px]"
              style={{ color: "var(--ink-faint)" }}
            >
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
                      title={alsoInGraph ? "also reached by traversal" : "similarity only"}
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
