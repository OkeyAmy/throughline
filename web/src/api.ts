export type Symbol = {
  id: number;
  name: string;
  repo: string;
  path: string;
  line: number;
};

export type ImpactRow = Symbol & {
  hop: number;
  cross_repo: boolean;
  is_test: boolean;
};

export type Trust = {
  exact: boolean;
  truncated_by: string | null;
  depth: number;
  max_depth: number;
  round_trips: number;
  ms: number;
  edge_types: string[];
  engine: string;
};

export type Totals = {
  impacted: number;
  shown: number;
  in_repos?: number;
  repos: Record<string, number>;
  tests: number;
  cross_repo: number;
};

export type Level = {
  depth: number;
  discovered: number;
  total: number;
  round_trips: number;
  frontier: number;
};

export type EvidencePath = {
  nodes: { id: number; name: string; repo: string; path: string }[];
  edges: { type: string; src: number; dst: number }[];
};

export async function health(): Promise<{ ok: boolean; nodes: number }> {
  const response = await fetch("/api/health");
  if (!response.ok) throw new Error(`health ${response.status}`);
  return response.json();
}

export async function searchSymbols(query: string): Promise<Symbol[]> {
  const response = await fetch(`/api/symbols?q=${encodeURIComponent(query)}&limit=8`);
  if (!response.ok) throw new Error(`search ${response.status}`);
  return (await response.json()).symbols;
}

export async function evidence(
  symbolId: number,
  fromId?: number,
): Promise<{ paths: EvidencePath[]; trust: { complete: boolean; ms: number } }> {
  const from = fromId !== undefined ? `&from_id=${fromId}` : "";
  const response = await fetch(`/api/evidence?symbol_id=${symbolId}${from}&max_len=5&path_count=12`);
  if (!response.ok) throw new Error(`evidence ${response.status}`);
  return response.json();
}

type StreamHandlers = {
  onSeed: (seed: Symbol) => void;
  onLevel: (level: Level) => void;
  onDone: (payload: { rows: ImpactRow[]; totals: Totals; trust: Trust }) => void;
  onError: (message: string) => void;
};

/**
 * Reads the level-by-level walk. Each `level` event is one BFS hop HydraDB has
 * finished serving — the frontier expanding is the work happening, not a spinner
 * standing in for it.
 */
export function streamImpact(
  symbolId: number,
  handlers: StreamHandlers,
): () => void {
  const source = new EventSource(`/api/impact/stream?symbol_id=${symbolId}&limit=400`);
  source.addEventListener("seed", (event) =>
    handlers.onSeed(JSON.parse((event as MessageEvent).data)),
  );
  source.addEventListener("level", (event) =>
    handlers.onLevel(JSON.parse((event as MessageEvent).data)),
  );
  source.addEventListener("done", (event) => {
    handlers.onDone(JSON.parse((event as MessageEvent).data));
    source.close();
  });
  source.addEventListener("error", (event) => {
    const data = (event as MessageEvent).data;
    handlers.onError(data ? JSON.parse(data).message : "stream failed");
    source.close();
  });
  return () => source.close();
}

export type PRResult = {
  pr: { owner: string; repo: string; number: number };
  changed_symbols: string[];
  seeds?: Symbol[];
  rows: ImpactRow[];
  totals: Totals;
  trust?: Trust & { seeds?: number };
  note?: string;
};

export async function impactOfPr(url: string): Promise<PRResult> {
  const response = await fetch("/api/impact/pr", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, limit: 400 }),
  });
  if (!response.ok) throw new Error((await response.json()).detail ?? `pr ${response.status}`);
  return response.json();
}

export type AskResult = {
  question: string;
  seed: Symbol;
  answer: string | null;
  rows: ImpactRow[];
  totals: Totals;
  trust: Trust;
};

export async function ask(question: string): Promise<AskResult> {
  const response = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, limit: 400 }),
  });
  if (!response.ok) throw new Error((await response.json()).detail ?? `ask ${response.status}`);
  return response.json();
}

export type BaselineResult = {
  files: string[];
  trust: { ms: number; corpus_files: number; engine: string; top_k: number };
};

export async function baseline(question: string, k = 15): Promise<BaselineResult> {
  const response = await fetch("/api/baseline", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, k }),
  });
  if (!response.ok) throw new Error((await response.json()).detail ?? `baseline ${response.status}`);
  return response.json();
}
