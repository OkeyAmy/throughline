import type { Trust } from "../api";

/**
 * Stat tiles, not a chart: five single values with no plot, so they follow the
 * tile spec — value in the display face, label recessive, no decoration.
 *
 * The first tile is the one that matters. A closure that hit a cap is a lower
 * bound, and saying so on screen is the difference between an answer and a guess.
 */
export function TrustStrip({ trust, nodes }: { trust: Trust | null; nodes: number | null }) {
  const tiles: { label: string; value: string; tone?: "good" | "warn" }[] = trust
    ? [
        {
          label: trust.exact ? "closure" : `cut short by ${trust.truncated_by}`,
          value: trust.exact ? "exact" : "partial",
          tone: trust.exact ? "good" : "warn",
        },
        { label: "depth reached", value: `${trust.depth}` },
        { label: "round trips", value: `${trust.round_trips}` },
        { label: "walk time", value: `${trust.ms} ms` },
        { label: "graph nodes", value: nodes ? nodes.toLocaleString() : "—" },
      ]
    : [];

  if (!trust) {
    return (
      <div className="border-t px-6 py-3 text-[11px]" style={{ borderColor: "var(--rule)", color: "var(--ink-faint)" }}>
        no walk yet — pick a symbol
      </div>
    );
  }

  return (
    <div
      className="grid grid-cols-2 border-t sm:grid-cols-5"
      style={{ borderColor: "var(--rule)" }}
    >
      {tiles.map((tile) => (
        <div
          key={tile.label}
          className="border-r border-b px-4 py-3 last:border-r-0"
          style={{ borderColor: "var(--rule)" }}
        >
          <div
            className="display text-[22px] leading-none"
            style={{
              color:
                tile.tone === "good"
                  ? "var(--good)"
                  : tile.tone === "warn"
                    ? "var(--warn)"
                    : "var(--ink)",
            }}
          >
            {tile.value}
          </div>
          <div className="section-marker mt-2">{tile.label}</div>
        </div>
      ))}
      <div
        className="col-span-2 px-4 py-2 text-[11px] sm:col-span-5"
        style={{ color: "var(--ink-faint)" }}
      >
        {trust.engine} · edges walked: {trust.edge_types.join(" · ")}
      </div>
    </div>
  );
}
