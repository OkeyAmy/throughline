"""`throughline wait` blocks until HydraDB can answer a query.

It exists because the node is not ready when the port opens — it accepts
connections, then rejects queries while it promotes a writer — and because the
image ships no wget or curl, so a container healthcheck cannot probe it.
"""

import pytest

from loader.wait import READINESS_PROBE, wait_for_ready


class FakeClient:
    """Fails `failures` times, then answers — the shape of a node still booting."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def scalar(self, _query: str):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("connection refused")
        return 0


def test_returns_as_soon_as_a_query_succeeds():
    client = FakeClient(failures=0)
    assert wait_for_ready(client, timeout=5, interval=0) is True
    # blindfold: invariant — a ready node must be probed exactly once.
    assert client.calls == 1


def test_keeps_trying_while_the_node_is_still_starting():
    client = FakeClient(failures=3)
    assert wait_for_ready(client, timeout=5, interval=0) is True
    # blindfold: math — three failures then a success is four calls.
    assert client.calls == 4


def test_gives_up_after_the_timeout_rather_than_hanging_a_deploy():
    client = FakeClient(failures=10_000)
    with pytest.raises(TimeoutError):
        wait_for_ready(client, timeout=0.05, interval=0.01)


def test_the_probe_is_a_real_query_not_a_socket_check():
    """A listening port is not proof: the node serves /readyz and then aborts on
    the first query if it is misconfigured (HydraDB's own README says so)."""
    seen = []

    class Recorder(FakeClient):
        def scalar(self, query: str):
            seen.append(query)
            return 0

    wait_for_ready(Recorder(failures=0), timeout=1, interval=0)
    # blindfold: contract — a bare `RETURN 1` is rejected by the engine, so the probe
    # is a MATCH that also works against an empty graph.
    assert seen == [READINESS_PROBE]
    assert READINESS_PROBE.startswith("MATCH ")
