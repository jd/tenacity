import asyncio
import typing
import unittest

from functools import wraps

from tenacity import RetryCallState, retry


def asynctest(
    callable_: typing.Callable[..., typing.Any],
) -> typing.Callable[..., typing.Any]:
    @wraps(callable_)
    def wrapper(*a: typing.Any, **kw: typing.Any) -> typing.Any:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(callable_(*a, **kw))

    return wrapper


MAX_RETRY_FIX_ATTEMPTS = 2


class TestIssue478(unittest.TestCase):
    def test_issue(self) -> None:
        results = []

        def do_retry(retry_state: RetryCallState) -> bool:
            outcome = retry_state.outcome
            assert outcome
            ex = outcome.exception()
            _subject_: str = retry_state.args[0]

            if _subject_ == "Fix":  # no retry on fix failure
                return False

            if retry_state.attempt_number >= MAX_RETRY_FIX_ATTEMPTS:
                return False

            if ex:
                do_fix_work()
                return True

            return False

        @retry(reraise=True, retry=do_retry)
        def _do_work(subject: str) -> None:
            if subject == "Error":
                results.append(f"{subject} is not working")
                raise Exception(f"{subject} is not working")
            results.append(f"{subject} is working")

        def do_any_work(subject: str) -> None:
            _do_work(subject)

        def do_fix_work() -> None:
            _do_work("Fix")

        try:
            do_any_work("Error")
        except Exception as exc:
            assert str(exc) == "Error is not working"
        else:
            assert False, "No exception caught"

        assert results == [
            "Error is not working",
            "Fix is working",
            "Error is not working",
        ]

    @asynctest
    async def test_async(self) -> None:
        results = []

        async def do_retry(retry_state: RetryCallState) -> bool:
            outcome = retry_state.outcome
            assert outcome
            ex = outcome.exception()
            _subject_: str = retry_state.args[0]

            if _subject_ == "Fix":  # no retry on fix failure
                return False

            if retry_state.attempt_number >= MAX_RETRY_FIX_ATTEMPTS:
                return False

            if ex:
                await do_fix_work()
                return True

            return False

        @retry(reraise=True, retry=do_retry)
        async def _do_work(subject: str) -> None:
            if subject == "Error":
                results.append(f"{subject} is not working")
                raise Exception(f"{subject} is not working")
            results.append(f"{subject} is working")

        async def do_any_work(subject: str) -> None:
            await _do_work(subject)

        async def do_fix_work() -> None:
            await _do_work("Fix")

        try:
            await do_any_work("Error")
        except Exception as exc:
            assert str(exc) == "Error is not working"
        else:
            assert False, "No exception caught"

        assert results == [
            "Error is not working",
            "Fix is working",
            "Error is not working",
        ]
