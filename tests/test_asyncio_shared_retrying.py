import asyncio
import unittest

from tenacity import AsyncRetrying, RetryCallState, stop_after_attempt, wait_none


class _FirstAttemptFails(Exception):
    pass


class TestOverlappingCallsOnSharedAsyncRetrying(unittest.TestCase):
    def test_finishing_iteration_keeps_the_state_of_a_newer_iteration(self) -> None:
        asyncio.run(asyncio.wait_for(self._overlap(), timeout=5))

    async def _overlap(self) -> None:
        release_b_before = asyncio.Event()
        release_a_predicate = asyncio.Event()
        a_in_predicate = asyncio.Event()
        b_attempting = asyncio.Event()
        a_finished = asyncio.Event()
        a_calls = 0

        async def before(retry_state: RetryCallState) -> None:
            if retry_state.args[0] == "B":
                await release_b_before.wait()

        async def retry_predicate(retry_state: RetryCallState) -> bool:
            if retry_state.args[0] == "A":
                a_in_predicate.set()
                await release_a_predicate.wait()
            assert retry_state.outcome is not None
            return retry_state.outcome.failed

        async def call_a(_: str) -> str:
            nonlocal a_calls
            a_calls += 1
            if a_calls == 1:
                raise _FirstAttemptFails
            return "a"

        async def call_b(_: str) -> str:
            b_attempting.set()
            await a_finished.wait()
            return "b"

        shared = AsyncRetrying(
            before=before,
            retry=retry_predicate,
            stop=stop_after_attempt(3),
            wait=wait_none(),
            reraise=True,
        )

        task_b: asyncio.Task[str] = asyncio.create_task(shared(call_b, "B"))
        await asyncio.sleep(0)
        task_a: asyncio.Task[str] = asyncio.create_task(shared(call_a, "A"))
        await a_in_predicate.wait()
        release_b_before.set()
        await b_attempting.wait()
        release_a_predicate.set()

        try:
            self.assertEqual(await task_a, "a")
            self.assertEqual(a_calls, 2)
        finally:
            # B must always finish: tenacity would retry a cancelled attempt
            a_finished.set()
        self.assertEqual(await task_b, "b")
