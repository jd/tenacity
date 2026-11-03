import asyncio

import pytest

from tenacity import (
    AsyncRetrying,
    IterState,
    RetryCallState,
    RetryError,
    stop_after_attempt,
)

from .test_asyncio import asynctest


@pytest.mark.parametrize("second_fails", [False, True])
@pytest.mark.parametrize("callback", ["retry", "after"])
@asynctest
async def test_concurrent_calls_keep_retry_actions(
    second_fails: bool, callback: str
) -> None:
    first_waiting = asyncio.Event()
    second_finished = asyncio.Event()
    attempts = {"first": 0, "second": 0}

    async def pause_first(state: RetryCallState) -> None:
        if state.args[0] == "first" and state.attempt_number == 1:
            first_waiting.set()
            await second_finished.wait()

    async def should_retry(state: RetryCallState) -> bool:
        if callback == "retry":
            await pause_first(state)
        assert state.outcome is not None
        return state.outcome.failed

    async def after(state: RetryCallState) -> None:
        if callback == "after":
            await pause_first(state)

    async def target(name: str) -> str:
        attempts[name] += 1
        if name == "first" and attempts[name] == 1:
            raise ValueError("retry first")
        if name == "second" and second_fails:
            raise ValueError("second failed")
        return name

    retrying = AsyncRetrying(
        retry=should_retry, after=after, stop=stop_after_attempt(2)
    )
    first: asyncio.Task[str] = asyncio.create_task(retrying(target, "first"))
    await first_waiting.wait()
    try:
        if second_fails:
            with pytest.raises(RetryError):
                await retrying(target, "second")
        else:
            assert await retrying(target, "second") == "second"
    finally:
        second_finished.set()

    assert await first == "first"
    assert attempts == {"first": 2, "second": 2 if second_fails else 1}


@asynctest
async def test_reentrant_call_keeps_outer_retry_actions() -> None:
    attempts = {"outer": 0, "inner": 0}

    async def should_retry(state: RetryCallState) -> bool:
        if state.args[0] == "outer" and state.attempt_number == 1:
            assert await retrying(target, "inner") == "inner"
        assert state.outcome is not None
        return state.outcome.failed

    async def target(name: str) -> str:
        attempts[name] += 1
        if name == "outer" and attempts[name] == 1:
            raise ValueError("retry outer")
        return name

    retrying = AsyncRetrying(retry=should_retry, stop=stop_after_attempt(2))
    assert await retrying(target, "outer") == "outer"
    assert attempts == {"outer": 2, "inner": 1}


@pytest.mark.parametrize("error", [ValueError, asyncio.CancelledError])
@asynctest
async def test_callback_failure_restores_iteration_state(
    error: type[BaseException],
) -> None:
    async def before(state: RetryCallState) -> None:
        assert retrying.iter_state is not previous_state
        raise error("callback failed")

    async def target() -> None:
        pytest.fail("the failed before callback should prevent the attempt")

    retrying = AsyncRetrying(before=before)
    previous_state = retrying.iter_state
    with pytest.raises(error, match="callback failed"):
        await retrying(target)
    assert retrying.iter_state is previous_state


@asynctest
async def test_nested_controllers_keep_their_own_iteration_state() -> None:
    outer_states: list[IterState] = []

    async def inner_before(state: RetryCallState) -> None:
        assert outer.iter_state is outer_states[-1]
        assert inner.iter_state is not outer.iter_state

    async def outer_before(state: RetryCallState) -> None:
        outer_states.append(outer.iter_state)
        assert await inner(target) == "ok"
        assert outer.iter_state is outer_states[-1]

    async def target() -> str:
        return "ok"

    inner = AsyncRetrying(before=inner_before)
    outer = AsyncRetrying(before=outer_before)
    previous_state = outer.iter_state
    assert await outer(target) == "ok"
    assert outer.iter_state is previous_state


@asynctest
async def test_iteration_context_does_not_affect_pickling() -> None:
    import pickle

    async def target() -> str:
        return "ok"

    retrying = AsyncRetrying(stop=stop_after_attempt(2))
    assert await retrying(target) == "ok"
    restored = pickle.loads(pickle.dumps(retrying))
    assert isinstance(restored, AsyncRetrying)
    assert await restored(target) == "ok"
    assert restored.statistics["attempt_number"] == 1


def test_trio_calls_keep_retry_actions() -> None:
    trio = pytest.importorskip("trio")

    async def run() -> None:
        first_waiting = trio.Event()
        second_finished = trio.Event()
        attempts = {"first": 0, "second": 0}
        results: list[str] = []

        async def should_retry(state: RetryCallState) -> bool:
            if state.args[0] == "first" and state.attempt_number == 1:
                first_waiting.set()
                await second_finished.wait()
            assert state.outcome is not None
            return state.outcome.failed

        async def target(name: str) -> str:
            attempts[name] += 1
            if name == "first" and attempts[name] == 1:
                raise ValueError("retry first")
            return name

        async def first_call() -> None:
            result: str = await retrying(target, "first")
            results.append(result)

        retrying = AsyncRetrying(retry=should_retry, stop=stop_after_attempt(2))
        async with trio.open_nursery() as nursery:
            nursery.start_soon(first_call)
            await first_waiting.wait()
            try:
                assert await retrying(target, "second") == "second"
            finally:
                second_finished.set()
        assert results == ["first"]
        assert attempts == {"first": 2, "second": 1}

    trio.run(run)


@pytest.mark.parametrize("callback", ["before", "retry"])
@asynctest
async def test_callback_child_does_not_retain_completed_controller(
    callback: str,
) -> None:
    import gc
    import weakref

    started = asyncio.Event()
    release = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []

    async def background() -> None:
        started.set()
        await release.wait()

    async def spawn_background() -> None:
        tasks.append(asyncio.create_task(background()))
        await started.wait()

    async def before(state: RetryCallState) -> None:
        if callback == "before":
            await spawn_background()

    async def should_retry(state: RetryCallState) -> bool:
        if callback == "retry":
            await spawn_background()
        return False

    async def target() -> str:
        return "ok"

    retrying = AsyncRetrying(before=before, retry=should_retry)
    controller_ref = weakref.ref(retrying)
    try:
        assert await retrying(target) == "ok"
        del retrying
        gc.collect()
        assert controller_ref() is None
    finally:
        release.set()
        await asyncio.gather(*tasks)
