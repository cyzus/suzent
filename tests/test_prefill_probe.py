import asyncio

import pytest

from suzent import streaming
from suzent.core import prefill_probe

_SGLANG_COUNTER = "sglang:prefill_effective_tokens_total"


def test_metrics_url_strips_the_v1_prefix() -> None:
    assert (
        prefill_probe.metrics_url("http://192.168.8.174:8888/v1")
        == "http://192.168.8.174:8888/metrics"
    )
    assert prefill_probe.metrics_url("http://host:8888/") == "http://host:8888/metrics"


def test_parse_progress_reads_a_labelled_counter() -> None:
    body = (
        "# HELP sglang:prefill_effective_tokens_total Prefill tokens.\n"
        "# TYPE sglang:prefill_effective_tokens_total counter\n"
        f'{_SGLANG_COUNTER}{{model_name="m",tp_rank="0"}} 2648538.0\n'
    )

    assert prefill_probe.parse_progress(body, (_SGLANG_COUNTER,)) == 2648538.0


def test_parse_progress_sums_tensor_parallel_ranks() -> None:
    # One series per rank; reading a single rank would under-report progress.
    body = "".join(
        f'{_SGLANG_COUNTER}{{tp_rank="{rank}"}} 100.0\n' for rank in range(4)
    )

    assert prefill_probe.parse_progress(body, (_SGLANG_COUNTER,)) == 400.0


def test_parse_progress_returns_none_for_an_unknown_exposition() -> None:
    assert prefill_probe.parse_progress("# nothing here\n", (_SGLANG_COUNTER,)) is None


def test_no_probe_for_a_hosted_provider() -> None:
    assert prefill_probe.make_prefill_probe("anthropic/claude-opus-5") is None
    assert prefill_probe.make_prefill_probe(None) is None
    assert prefill_probe.make_prefill_probe("no-slash") is None


class _NeverArrives:
    """A stream whose first event never comes."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Event().wait()


async def _first_event(stream, deadline, probe):
    return await streaming._await_model_event(stream, deadline, probe)


async def test_without_a_probe_the_deadline_still_applies() -> None:
    with pytest.raises(asyncio.TimeoutError):
        await _first_event(_NeverArrives(), 0.05, None)


async def test_a_stalled_server_fails_before_the_deadline(monkeypatch) -> None:
    monkeypatch.setattr(streaming, "_PREFILL_PROBE_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(streaming, "_PREFILL_STALL_LIMIT_SECONDS", 0.05)

    async def frozen():
        return 1000.0

    # Deadline is effectively infinite; the stall is what ends the wait.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(_first_event(_NeverArrives(), 1e6, frozen), timeout=5)


async def test_a_working_server_outlives_its_deadline(monkeypatch) -> None:
    monkeypatch.setattr(streaming, "_PREFILL_PROBE_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(streaming, "_PREFILL_STALL_LIMIT_SECONDS", 0.05)
    progress = iter(range(1, 10_000))

    async def advancing():
        return float(next(progress))

    # A 1ms deadline the server blows straight past while visibly working.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            _first_event(_NeverArrives(), 0.001, advancing), timeout=0.4
        )
    # Timed out on the *outer* 0.4s guard, not the 0.001s deadline -- i.e. the
    # probe kept the wait alive far past what the deadline alone would allow.


async def test_progress_then_stall_ends_the_wait(monkeypatch) -> None:
    monkeypatch.setattr(streaming, "_PREFILL_PROBE_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(streaming, "_PREFILL_STALL_LIMIT_SECONDS", 0.05)
    values = [1.0, 2.0, 3.0] + [3.0] * 500

    async def then_frozen():
        return values.pop(0)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(_first_event(_NeverArrives(), 1e6, then_frozen), 5)


async def test_an_unavailable_probe_degrades_to_the_deadline(monkeypatch) -> None:
    monkeypatch.setattr(streaming, "_PREFILL_PROBE_INTERVAL_SECONDS", 0.01)

    async def unavailable():
        return None

    # None means "cannot tell", never "stalled": the plain deadline decides.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(_first_event(_NeverArrives(), 0.05, unavailable), 5)


async def test_the_first_event_is_returned_when_it_arrives() -> None:
    class _Arrives:
        def __aiter__(self):
            return self

        async def __anext__(self):
            return "event"

    async def probe():
        return 1.0

    assert await _first_event(_Arrives(), 5.0, probe) == "event"


async def test_stop_iteration_propagates() -> None:
    class _Empty:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    with pytest.raises(StopAsyncIteration):
        await _first_event(_Empty(), 5.0, None)


async def test_the_idle_wait_also_gets_the_probe(monkeypatch) -> None:
    """The wait after a tool result is another prefill, not an idle model."""
    monkeypatch.setattr(streaming, "_PREFILL_PROBE_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(streaming, "_PREFILL_STALL_LIMIT_SECONDS", 0.05)
    monkeypatch.setattr(streaming, "_STREAM_IDLE_TIMEOUT_SECONDS", 0.001)
    progress = iter(range(1, 10_000))

    async def advancing():
        return float(next(progress))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            _first_event(
                _NeverArrives(), streaming._STREAM_IDLE_TIMEOUT_SECONDS, advancing
            ),
            timeout=0.4,
        )
