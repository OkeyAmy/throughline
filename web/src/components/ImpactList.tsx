import { Fragment } from "react";
import type { ImpactRow } from "../api";

type Props = {
  rows: ImpactRow[];
  seedRepo: string;
  filter: "all" | "cross" | "tests";
  onFilter: (filter: "all" | "cross" | "tests") => void;
  selected: number | null;
  onSelect: (row: ImpactRow) => void;
};

const FILTERS: { key: Props["filter"]; label: string }[] = [
  { key: "all", label: "everything" },
  { key: "cross", label: "other repos" },
  { key: "tests", label: "tests to run" },
];

function hopLabel(hop: number): string {
  if (hop <= 1) return "directly connected";
  if (hop === 2) return "one step away";
  return "further downstream";
}

function Row({
  row,
  seedRepo,
  isSelected,
  onSelect,
}: {
  row: ImpactRow;
  seedRepo: string;
  isSelected: boolean;
  onSelect: (row: ImpactRow) => void;
}) {
  return (
    <li>
      <button
        onClick={() => onSelect(row)}
        className="flex w-full items-baseline gap-3 border-b px-6 py-2 text-left"
        style={{
          borderColor: "var(--rule)",
          background: isSelected ? "var(--surface-1)" : "transparent",
        }}
      >
        <span
          className="w-6 shrink-0 text-[11px] tabular-nums"
          style={{ color: "var(--ink-faint)" }}
          title={`${row.hop} hop${row.hop === 1 ? "" : "s"} from the change`}
        >
          {row.hop}
        </span>
        <span
          className="w-14 shrink-0 truncate text-[11px]"
          style={{ color: row.cross_repo ? "var(--series-cross)" : "var(--ink-dim)" }}
        >
          {row.repo}
        </span>
        <span className="min-w-0 flex-1 truncate" style={{ color: "var(--ink)" }}>
          {row.name}
        </span>
        <span
          className="min-w-0 max-w-[45%] shrink truncate text-[11px]"
          style={{ color: "var(--ink-faint)" }}
        >
          {row.path}
          {row.line > 0 ? `:${row.line}` : ""}
        </span>
        {row.is_test && (
          <span
            className="shrink-0 border px-1 text-[10px] uppercase tracking-wider"
            style={{ borderColor: "var(--rule)", color: "var(--ink-dim)" }}
          >
            test
          </span>
        )}
        {row.cross_repo && (
          <span
            className="shrink-0 border px-1 text-[10px] uppercase tracking-wider"
            style={{ borderColor: "var(--series-cross)", color: "var(--series-cross)" }}
            title={`defined in ${seedRepo}, reached in ${row.repo}`}
          >
            cross-repo
          </span>
        )}
      </button>
    </li>
  );
}

function GroupHeader({ hop, count }: { hop: number; count: number }) {
  return (
    <li
      className="section-marker border-b px-6 py-1.5"
      style={{ borderColor: "var(--rule)", background: "var(--surface-1)", color: "var(--ink-faint)" }}
    >
      hop {hop} — {hopLabel(hop)} ({count})
    </li>
  );
}

export function ImpactList({ rows, seedRepo, filter, onFilter, selected, onSelect }: Props) {
  const visible = rows.filter((row) =>
    filter === "cross" ? row.cross_repo : filter === "tests" ? row.is_test : true,
  );
  const testsCount = rows.filter((row) => row.is_test).length;
  const crossCount = rows.filter((row) => row.cross_repo).length;
  const counts: Record<Props["filter"], number> = {
    all: rows.length,
    cross: crossCount,
    tests: testsCount,
  };

  const groups: { hop: number; rows: ImpactRow[] }[] = [];
  for (const row of visible) {
    const last = groups[groups.length - 1];
    if (last && last.hop === row.hop) last.rows.push(row);
    else groups.push({ hop: row.hop, rows: [row] });
  }
  const primaryGroups = groups.filter((group) => group.hop <= 2);
  const restGroups = groups.filter((group) => group.hop > 2);
  const restCount = restGroups.reduce((sum, group) => sum + group.rows.length, 0);
  const restHops = restGroups.map((group) => group.hop);
  const restRange =
    restHops.length > 1 ? `hop ${restHops[0]}–${restHops[restHops.length - 1]}` : `hop ${restHops[0]}`;

  return (
    <section className="flex flex-col lg:min-h-0 lg:flex-1">
      <header
        className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2 border-b px-6 py-3"
        style={{ borderColor: "var(--rule)" }}
      >
        <div className="flex items-baseline gap-3">
          <span className="section-marker">02 / blast radius</span>
          <span className="text-[11px]" style={{ color: "var(--ink-faint)" }}>
            {visible.length} shown
          </span>
        </div>
        <div className="flex gap-1">
          {FILTERS.map((option) => (
            <button
              key={option.key}
              onClick={() => onFilter(option.key)}
              className="border px-2 py-1 text-[11px]"
              style={{
                borderColor: filter === option.key ? "var(--ink)" : "var(--rule)",
                color: filter === option.key ? "var(--ink)" : "var(--ink-dim)",
                background: filter === option.key ? "var(--surface-2)" : "transparent",
              }}
            >
              {option.label} ({counts[option.key]})
            </button>
          ))}
        </div>
      </header>

      <ol className="lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
        {primaryGroups.map((group) => (
          <Fragment key={`h-${group.hop}`}>
            <GroupHeader hop={group.hop} count={group.rows.length} />
            {group.rows.map((row) => (
              <Row
                key={row.id}
                row={row}
                seedRepo={seedRepo}
                isSelected={selected === row.id}
                onSelect={onSelect}
              />
            ))}
          </Fragment>
        ))}

        {restGroups.length > 0 && (
          <li>
            <details>
              <summary
                className="cursor-pointer border-b px-6 py-2 text-[11px]"
                style={{ borderColor: "var(--rule)", color: "var(--ink-faint)" }}
              >
                show {restCount} more at {restRange}
              </summary>
              <ol>
                {restGroups.map((group) => (
                  <Fragment key={`h-${group.hop}`}>
                    <GroupHeader hop={group.hop} count={group.rows.length} />
                    {group.rows.map((row) => (
                      <Row
                        key={row.id}
                        row={row}
                        seedRepo={seedRepo}
                        isSelected={selected === row.id}
                        onSelect={onSelect}
                      />
                    ))}
                  </Fragment>
                ))}
              </ol>
            </details>
          </li>
        )}

        {visible.length === 0 && (
          <li className="px-6 py-6 text-[12px]" style={{ color: "var(--ink-faint)" }}>
            {filter === "cross"
              ? "nothing outside this repo — the change is contained"
              : filter === "tests"
                ? "no tests reach this symbol, which is its own finding"
                : "no impact found"}
          </li>
        )}
      </ol>
    </section>
  );
}
