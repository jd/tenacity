import asyncio
from collections.abc import Awaitable, Callable

import pytest

from tenacity import AsyncRetrying, retry, stop_after_attempt, wait_fixed


def _make_sleep(
    kind: str, events: list[str], delays: list[float]
) -> Callable[[int | float], Awaitable[None] | None]:
    async def complete() -> None:
        await asyncio.sleep(0)
        events.append("sleep:done")

    def sleep(seconds: float) -> Awaitable[None] | None:
        delays.append(float(seconds))
        events.append("sleep:start")
        if kind == "sync" or (kind == "mixed" and len(delays) == 1):
            events.append("sleep:done")
            return None
        if kind == "future":
            loop = asyncio.get_running_loop()
            future: asyncio.Future[None] = loop.create_future()

            def finish() -> None:
                events.append("sleep:done")
                future.set_result(None)

            loop.call_soon(finish)
            return future
        if kind == "task":
            return asyncio.create_task(complete())
        return complete()

    if kind == "async":

        async def async_sleep(seconds: float) -> None:
            delays.append(float(seconds))
            events.append("sleep:start")
            await complete()

        return async_sleep
    return sleep


async def _exercise(
    mode: str,
    sleep: Callable[[int | float], Awaitable[None] | None],
    events: list[str],
) -> None:
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        events.append("operation")
        if calls < 3:
            raise OSError("temporary failure")
        return "ok"

    retrying = AsyncRetrying(
        sleep=sleep, wait=wait_fixed(0.25), stop=stop_after_attempt(3)
    )
    if mode == "iterator":
        result = ""
        async for attempt in retrying:
            with attempt:
                result = await operation()
        assert result == "ok"
    elif mode == "decorator":
        wrapped = retry(
            # The decorator overloads do not admit mixed sleep return types.
            sleep=sleep,  # type: ignore[arg-type]
            wait=wait_fixed(0.25),
            stop=stop_after_attempt(3),
        )(operation)
        assert await wrapped() == "ok"
    else:
        assert await retrying(operation) == "ok"
    assert calls == 3


@pytest.mark.parametrize("mode", ["call", "iterator", "decorator"])
@pytest.mark.parametrize(
    "kind", ["sync", "async", "coroutine", "task", "future", "mixed"]
)
def test_sleep_callback_completes_before_next_attempt(mode: str, kind: str) -> None:
    events: list[str] = []
    delays: list[float] = []
    sleep = _make_sleep(kind, events, delays)

    asyncio.run(_exercise(mode, sleep, events))

    assert delays == [0.25, 0.25]
    assert events == [
        "operation",
        "sleep:start",
        "sleep:done",
        "operation",
        "sleep:start",
        "sleep:done",
        "operation",
    ]


@pytest.mark.parametrize("mode", ["call", "iterator", "decorator"])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_sleep_callback_failure_propagates(mode: str, asynchronous: bool) -> None:
    events: list[str] = []
    error = RuntimeError("sleep failed")

    def sleep(seconds: float) -> None:
        raise error

    async def async_sleep(seconds: float) -> None:
        await asyncio.sleep(0)
        raise error

    with pytest.raises(RuntimeError, match="sleep failed") as caught:
        asyncio.run(_exercise(mode, async_sleep if asynchronous else sleep, events))

    assert caught.value is error
    assert events == ["operation"]
