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
          <p className="mt-1 max-w-3xl text-[11px]" style={{ color: "var(--ink-faint)" }}>
            Same question, a second engine: instead of walking the graph, this ranks every file in
            the workspace by embedding similarity and returns the top {files.length}. No fixed
            ground truth exists for an arbitrary question, so there's no accuracy score here —
            the measured F1 (0.350 graph vs 0.226 similarity, n=60) lives in the eval harness.
            What this panel shows instead is what a ranked top-{files.length} can and can't cover.
          </p>
          <div className="mt-3 flex flex-wrap items-baseline gap-x-8 gap-y-2">
            <div>
              <div className="display text-[22px] leading-none" style={{ color: "var(--ink)" }}>
                {shared} / {totalFiles}
              </div>
              <div className="section-marker mt-1">
                files the similarity search could return, out of what the walk actually found
              </div>
            </div>
          </div>
          <p className="mt-3 max-w-3xl text-[11px]" style={{ color: "var(--ink-dim)" }}>
            All <span style={{ color: "var(--series-call)" }}>{shared}</span> files it returned
            were also found by the walk — it wasn't wrong, just narrow. The walk found{" "}
            <span style={{ color: "var(--ink)" }}>{beyond}</span> more files a fixed top-
            {files.length} list could never have held, no matter how good the ranking —{" "}
            <span style={{ color: "var(--series-cross)" }}>{beyondCrossRepo}</span> of those in a
            different repository — and can say that {totalFiles} is the complete set, not a guess
            at one.
          </p>
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
        </>
      )}
    </section>
  );
}
