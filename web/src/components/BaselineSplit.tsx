import type { ImpactRow } from "../api";

/**
 * The comparison, live: the same question answered by embedding similarity over
 * the same corpus.
 *
 * This panel does not claim the baseline is wrong — on this workspace it usually
 * is not, and the measured numbers are in eval_harness/results.md. It shows the
 * difference in *kind*: similarity ranks a fixed handful, traversal enumerates a
 * closure and can say how far it went. Overlap is marked, and so is what the walk
 * found that a top-k could not have contained.
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
  const reached = new Set(rows.map((row) => row.path));
  const shared = files.filter((file) => reached.has(file)).length;
  const beyond = reached.size - shared;
  const crossRepo = rows.filter((row) => row.cross_repo).length;

  return (
    <section className="border-t px-6 py-4" style={{ borderColor: "var(--rule)" }}>
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="section-marker">04 / the same question, by similarity</span>
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
          <p className="mt-2 max-w-3xl text-[11px]" style={{ color: "var(--ink-dim)" }}>
            <span style={{ color: "var(--series-call)" }}>{shared}</span> of its{" "}
            {files.length} files are also in the traversal's answer
            {files.length - shared > 0 && (
              <>
                ; <span style={{ color: "var(--series-cross)" }}>{files.length - shared}</span> are
                not
              </>
            )}
            . The walk returned{" "}
            <span style={{ color: "var(--ink)" }}>{beyond}</span> more that a top-{files.length}{" "}
            could not have held —{" "}
            <span style={{ color: "var(--series-cross)" }}>{crossRepo}</span> of them in another
            repository — and it can say whether that set is complete. Similarity ranks; traversal
            enumerates.
          </p>
          <ul className="mt-2 grid gap-x-6 gap-y-1 md:grid-cols-2">
            {files.map((file) => {
              const alsoInGraph = reached.has(file);
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
        </>
      )}
    </section>
  );
}
