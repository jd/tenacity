import asyncio
import gc
import typing
import unittest

import tenacity
from tenacity import retry, stop_after_attempt, wait_none


@retry(stop=stop_after_attempt(3), wait=wait_none(), reraise=True)
def _succeeds() -> int:
    return 1


class _FailsOnce:
    def __init__(self) -> None:
        self.calls = 0

    def check(self) -> None:
        self.calls += 1
        if self.calls % 2:
            raise ValueError("fails once")


_sync_fails_once = _FailsOnce()
_async_fails_once = _FailsOnce()


@retry(stop=stop_after_attempt(3), wait=wait_none(), reraise=True)
def _succeeds_after_one_retry() -> int:
    _sync_fails_once.check()
    return 1


@retry(stop=stop_after_attempt(3), wait=wait_none(), reraise=True)
async def _async_succeeds() -> int:
    return 1


@retry(stop=stop_after_attempt(3), wait=wait_none(), reraise=True)
async def _async_succeeds_after_one_retry() -> int:
    _async_fails_once.check()
    return 1


def _retrying_objects_in_cyclic_garbage(call: typing.Callable[[], object]) -> int:
    call()
    gc.collect()
    was_enabled = gc.isenabled()
    gc.disable()
    gc.set_debug(gc.DEBUG_SAVEALL)
    try:
        call()
        gc.collect()
        # type(), not isinstance(): the garbage can hold dead weakref proxies
        return sum(issubclass(type(obj), tenacity.BaseRetrying) for obj in gc.garbage)
    finally:
        gc.set_debug(0)
        gc.garbage.clear()
        if was_enabled:
            gc.enable()
        gc.collect()


class TestNoReferenceCycles(unittest.TestCase):
    def test_successful_call(self) -> None:
        self.assertEqual(_retrying_objects_in_cyclic_garbage(_succeeds), 0)

    def test_call_that_retries_once(self) -> None:
        self.assertEqual(
            _retrying_objects_in_cyclic_garbage(_succeeds_after_one_retry), 0
        )

    def test_async_successful_call(self) -> None:
        self.assertEqual(
            _retrying_objects_in_cyclic_garbage(lambda: asyncio.run(_async_succeeds())),
            0,
        )

    def test_async_call_that_retries_once(self) -> None:
        self.assertEqual(
            _retrying_objects_in_cyclic_garbage(
                lambda: asyncio.run(_async_succeeds_after_one_retry())
            ),
            0,
        )
