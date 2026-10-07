import asyncio
from typing import Any

import pytest

from tenacity import AsyncRetrying, RetryCallState, Retrying, stop_after_attempt


class _Wait:
    def __init__(self) -> None:
        self.attempts: list[int] = []

    def __call__(self, state: RetryCallState) -> float:
        self.attempts.append(state.attempt_number)
        return state.attempt_number / 4


class _FalseWait(_Wait):
    def __bool__(self) -> bool:
        return False


class _EmptyWait(_Wait):
    def __len__(self) -> int:
        return 0


class _NoTruthTestWait(_Wait):
    def __bool__(self) -> bool:
        raise AssertionError("A callable wait strategy must not be truth-tested")


class _AsyncFalseWait:
    def __init__(self) -> None:
        self.attempts: list[int] = []

    def __bool__(self) -> bool:
        return False

    async def __call__(self, state: RetryCallState) -> float:
        await asyncio.sleep(0)
        self.attempts.append(state.attempt_number)
        return state.attempt_number / 4


@pytest.mark.parametrize("wait_type", [_Wait, _FalseWait, _EmptyWait, _NoTruthTestWait])
def test_sync_callable_wait(wait_type: type[_Wait]) -> None:
    wait = wait_type()
    sleeps: list[float] = []
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("temporary failure")
        return "ok"

    retrying = Retrying(wait=wait, sleep=sleeps.append, stop=stop_after_attempt(3))

    assert retrying(operation) == "ok"
    assert calls == 3
    assert wait.attempts == [1, 2]
    assert sleeps == [0.25, 0.5]
    assert retrying.statistics["idle_for"] == 0.75


@pytest.mark.parametrize(
    "wait_type", [_Wait, _FalseWait, _EmptyWait, _NoTruthTestWait, _AsyncFalseWait]
)
def test_async_callable_wait(wait_type: type[_Wait] | type[_AsyncFalseWait]) -> None:
    wait = wait_type()
    sleeps: list[float] = []
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("temporary failure")
        return "ok"

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    retrying = AsyncRetrying(
        wait=wait,  # type: ignore[arg-type]
        sleep=sleep,
        stop=stop_after_attempt(3),
    )

    assert asyncio.run(retrying(operation)) == "ok"
    assert calls == 3
    assert wait.attempts == [1, 2]
    assert sleeps == [0.25, 0.5]
    assert retrying.statistics["idle_for"] == 0.75


@pytest.mark.parametrize("wait", [None, 0, False, ""])
def test_falsey_non_callable_wait_remains_disabled(wait: Any) -> None:
    sync_sleeps: list[float] = []
    async_sleeps: list[float] = []

    def operation() -> None:
        raise OSError("temporary failure")

    async def async_operation() -> None:
        operation()

    async def sleep(seconds: float) -> None:
        async_sleeps.append(seconds)

    sync_retrying = Retrying(
        wait=wait, sleep=sync_sleeps.append, stop=stop_after_attempt(2), reraise=True
    )
    async_retrying = AsyncRetrying(
        wait=wait, sleep=sleep, stop=stop_after_attempt(2), reraise=True
    )

    with pytest.raises(OSError, match="temporary failure"):
        sync_retrying(operation)
    with pytest.raises(OSError, match="temporary failure"):
        asyncio.run(async_retrying(async_operation))

    assert sync_sleeps == [0]
    assert async_sleeps == [0]


@pytest.mark.parametrize("wait", [1, "invalid"])
def test_truthy_non_callable_wait_still_raises(wait: Any) -> None:
    def operation() -> None:
        raise OSError("temporary failure")

    async def async_operation() -> None:
        operation()

    with pytest.raises(TypeError, match="not callable"):
        Retrying(wait=wait, stop=stop_after_attempt(2))(operation)
    with pytest.raises(TypeError, match="not callable"):
        asyncio.run(
            AsyncRetrying(wait=wait, stop=stop_after_attempt(2))(async_operation)
        )
