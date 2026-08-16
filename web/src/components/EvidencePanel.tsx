import type { EvidencePath } from "../api";

const EDGE_COLOR: Record<string, string> = {
  CALLED_BY: "var(--series-call)",
  IMPORTED_BY: "var(--series-import)",
  PROVIDED_BY: "var(--series-cross)",
};

/**
 * Evidence paths as hop chains. Each hop is labelled with its edge type — colour
 * carries identity for the three that matter and every one is written out, so the
 * chain reads the same in greyscale.
 *
 * These come from HydraDB's path procedure and are a sample at depth. The panel
 * says so rather than implying the list is the whole truth.
 */
export function EvidencePanel({
  paths,
  complete,
  ms,
  seedName,
  loading,
}: {
  paths: EvidencePath[];
  complete: boolean;
  ms: number;
  seedName: string;
  loading: boolean;
}) {
  return (
    <aside
      className="panel-in flex w-full min-w-0 flex-col border-l lg:w-[420px]"
      style={{ borderColor: "var(--rule)" }}
    >
      <header className="border-b px-5 py-3" style={{ borderColor: "var(--rule)" }}>
        <span className="section-marker">03 / evidence</span>
        <p className="mt-1 text-[11px]" style={{ color: "var(--ink-faint)" }}>
          {loading
            ? "walking paths…"
            : `${paths.length} paths out of ${seedName} · ${ms} ms · algo.SSpaths`}
        </p>
        {!loading && !complete && (
          <p className="mt-1 text-[11px]" style={{ color: "var(--warn)" }}>
            sample, not the full set — more paths exist than were returned
          </p>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {paths.map((path, index) => (
          <div
            key={index}
            className="level-land mb-4 border-b pb-4 last:border-b-0"
            style={{ borderColor: "var(--rule)", animationDelay: `${Math.min(index, 8) * 40}ms` }}
          >
            {path.nodes.map((node, hop) => {
              const edge = path.edges[hop - 1];
              return (
                <div key={`${node.id}-${hop}`}>
                  {edge && (
                    <div className="flex items-center gap-2 py-1 pl-2 text-[10px]">
                      <span
                        aria-hidden
                        className="inline-block h-4 w-px"
                        style={{ background: EDGE_COLOR[edge.type] ?? "var(--rule)" }}
                      />
                      <span
                        className="uppercase tracking-wider text-[11px]"
                        style={{ color: EDGE_COLOR[edge.type] ?? "var(--ink-faint)" }}
                      >
                        {edge.type.toLowerCase().replace(/_/g, " ")}
                      </span>
                    </div>
                  )}
                  <div className="flex items-baseline gap-2">
                    <span style={{ color: "var(--ink)" }}>{node.name}</span>
                    {node.repo && (
                      <span className="text-[10px]" style={{ color: "var(--ink-faint)" }}>
                        {node.repo}
                      </span>
                    )}
                  </div>
                  {node.path && (
                    <div className="truncate text-[12px]" style={{ color: "var(--ink-faint)" }}>
                      {node.path}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}

        {!loading && paths.length === 0 && (
          <p className="text-[12px]" style={{ color: "var(--ink-faint)" }}>
            nothing reaches this symbol
          </p>
        )}
      </div>
    </aside>
  );
}
