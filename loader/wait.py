"""Block until HydraDB can answer a query.

Two reasons this is a client-side wait rather than a container healthcheck: the
image ships neither `wget` nor `curl`, so an in-container HTTP probe cannot run;
and a listening port is not readiness — the node serves `/readyz` and can still
reject queries while it promotes a writer.

The probe is therefore a real query, which is the same bar HydraDB's own README
sets: "a listening port is not proof; a round-tripped write is".
"""

from __future__ import annotations

import time
from typing import Protocol


#: A bare `RETURN 1` is rejected — "row execution supports MATCH ... RETURN queries"
#: — so the probe counts nodes instead. It works on an empty graph and still proves
#: the engine is executing, not merely listening.
READINESS_PROBE = "MATCH (n:Sym) RETURN count(*) AS c"


class Queryable(Protocol):
    def scalar(self, query: str): ...


def wait_for_ready(client: Queryable, timeout: float = 120.0, interval: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while True:
        try:
            client.scalar(READINESS_PROBE)
            return True
        except Exception as exc:  # noqa: BLE001 — anything means "not ready yet"
            last = exc
        if time.monotonic() >= deadline:
            raise TimeoutError(f"HydraDB not ready after {timeout}s: {last}")
        time.sleep(interval)
