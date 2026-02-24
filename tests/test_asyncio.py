# Copyright 2016 Étienne Bersac
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import inspect
import unittest
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, TypeVar
from unittest import mock

try:
    import trio
except ImportError:
    have_trio = False
else:
    have_trio = True

import pytest

import tenacity
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    RetryError,
    retry,
    retry_if_exception,
    retry_if_result,
    stop_after_attempt,
)
from tenacity import asyncio as tasyncio
from tenacity.wait import wait_fixed

from .test_tenacity import (
    NoIOErrorAfterCount,
    NoneReturnUntilAfterCount,
    current_time_ms,
)

_F = TypeVar("_F", bound=Callable[..., Coroutine[Any, Any, Any]])


def asynctest(callable_: _F) -> Callable[..., Any]:
    @wraps(callable_)
    def wrapper(*a: Any, **kw: Any) -> Any:
        return asyncio.run(callable_(*a, **kw))

    return wrapper


async def _async_function(thing: NoIOErrorAfterCount) -> Any:
    await asyncio.sleep(0.00001)
    return thing.go()


@retry
async def _retryable_coroutine(thing: NoIOErrorAfterCount) -> Any:
    await asyncio.sleep(0.00001)
    return thing.go()


@retry(stop=stop_after_attempt(2))
async def _retryable_coroutine_with_2_attempts(thing: NoIOErrorAfterCount) -> Any:
    await asyncio.sleep(0.00001)
    return thing.go()


class TestAsyncio(unittest.TestCase):
    @asynctest
    async def test_retry(self) -> None:
        thing = NoIOErrorAfterCount(5)
        await _retryable_coroutine(thing)
        assert thing.counter == thing.count

    @asynctest
    async def test_iscoroutinefunction(self) -> None:
        assert asyncio.iscoroutinefunction(_retryable_coroutine)
        assert inspect.iscoroutinefunction(_retryable_coroutine)

    @asynctest
    async def test_retry_using_async_retying(self) -> None:
        thing = NoIOErrorAfterCount(5)
        retrying = AsyncRetrying()
        await retrying(_async_function, thing)
        assert thing.counter == thing.count

    @asynctest
    async def test_stop_after_attempt(self) -> None:
        thing = NoIOErrorAfterCount(2)
        try:
            await _retryable_coroutine_with_2_attempts(thing)
        except RetryError:
            assert thing.counter == 2

    def test_repr(self) -> None:
        repr(tasyncio.AsyncRetrying())

    def test_retry_attributes(self) -> None:
        assert hasattr(_retryable_coroutine, "retry")
        assert hasattr(_retryable_coroutine, "retry_with")

    def test_retry_preserves_argument_defaults(self) -> None:
        async def function_with_defaults(a: int = 1) -> int:
            return a

        async def function_with_kwdefaults(*, a: int = 1) -> int:
            return a

        retrying = AsyncRetrying(
            wait=tenacity.wait_fixed(0.01), stop=tenacity.stop_after_attempt(3)
        )
        wrapped_defaults_function = retrying.wraps(function_with_defaults)
        wrapped_kwdefaults_function = retrying.wraps(function_with_kwdefaults)

        self.assertEqual(
            function_with_defaults.__defaults__,
            wrapped_defaults_function.__defaults__,  # type: ignore[attr-defined]
        )
        self.assertEqual(
            function_with_kwdefaults.__kwdefaults__,
            wrapped_kwdefaults_function.__kwdefaults__,  # type: ignore[attr-defined]
        )

    @asynctest
    async def test_attempt_number_is_correct_for_interleaved_coroutines(self) -> None:
        attempts: list[Any] = []

        def after(retry_state: RetryCallState) -> None:
            attempts.append((retry_state.args[0], retry_state.attempt_number))

        thing1 = NoIOErrorAfterCount(3)
        thing2 = NoIOErrorAfterCount(3)

        await asyncio.gather(
            _retryable_coroutine.retry_with(after=after)(thing1),
            _retryable_coroutine.retry_with(after=after)(thing2),
        )

        # There's no waiting on retry, only a wait in the coroutine, so the
        # executions should be interleaved.
        even_thing_attempts = attempts[::2]
        things, attempt_nos1 = zip(*even_thing_attempts)
        assert len(set(things)) == 1
        assert list(attempt_nos1) == [1, 2, 3]

        odd_thing_attempts = attempts[1::2]
        things, attempt_nos2 = zip(*odd_thing_attempts)
        assert len(set(things)) == 1
        assert list(attempt_nos2) == [1, 2, 3]


class TestAsyncEnabled(unittest.TestCase):
    @asynctest
    async def test_enabled_false_skips_retry(self) -> None:
        """When enabled=False, async function is called directly without retrying."""
        call_count = 0

        @retry(enabled=False, stop=stop_after_attempt(3))
        async def always_fails() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError, match="fail"):
            await always_fails()
        assert call_count == 1


@unittest.skipIf(not have_trio, "trio not installed")
class TestTrio(unittest.TestCase):
    def test_trio_basic(self) -> None:
        thing = NoIOErrorAfterCount(5)

        @retry
        async def trio_function() -> Any:
            await trio.sleep(0.00001)
            return thing.go()

        trio.run(trio_function)

        assert thing.counter == thing.count


class TestContextManager(unittest.TestCase):
    @asynctest
    async def test_do_max_attempts(self) -> None:
        attempts = 0
        retrying = tasyncio.AsyncRetrying(stop=stop_after_attempt(3))
        try:
            async for attempt in retrying:
                with attempt:
                    attempts += 1
                    raise Exception
        except RetryError:
            pass

        assert attempts == 3

    @asynctest
    async def test_reraise(self) -> None:
        class CustomError(Exception):
            pass

        try:
            async for attempt in tasyncio.AsyncRetrying(
                stop=stop_after_attempt(1), reraise=True
            ):
                with attempt:
                    raise CustomError()
        except CustomError:
            pass
        else:
            raise Exception

    @asynctest
    async def test_sleeps(self) -> None:
        start = current_time_ms()
        try:
            async for attempt in tasyncio.AsyncRetrying(
                stop=stop_after_attempt(1), wait=wait_fixed(1)
            ):
                with attempt:
                    raise Exception()
        except RetryError:
            pass
        t = current_time_ms() - start
        self.assertLess(t, 1.1)

    @asynctest
    async def test_retry_with_result(self) -> None:
        async def test() -> int:
            attempts = 0

            # mypy doesn't have great lambda support
            def lt_3(x: float) -> bool:
                return x < 3

            async for attempt in tasyncio.AsyncRetrying(retry=retry_if_result(lt_3)):
                with attempt:
                    attempts += 1
                attempt.retry_state.set_result(attempts)
            return attempts

        result = await test()

        self.assertEqual(3, result)

    @asynctest
    async def test_retry_with_async_result(self) -> None:
        async def test() -> int:
            attempts = 0

            async def lt_3(x: float) -> bool:
                return x < 3

            async for attempt in tasyncio.AsyncRetrying(
                retry=tasyncio.retry_if_result(lt_3)
            ):
                with attempt:
                    attempts += 1

                assert attempt.retry_state.outcome  # help mypy
                if not attempt.retry_state.outcome.failed:
                    attempt.retry_state.set_result(attempts)

            return attempts

        result = await test()

        self.assertEqual(3, result)

    @asynctest
    async def test_retry_with_async_exc(self) -> None:
        async def test() -> int:
            attempts = 0

            class CustomException(Exception):
                pass

            async def is_exc(e: BaseException) -> bool:
                return isinstance(e, CustomException)

            async for attempt in tasyncio.AsyncRetrying(
                retry=tasyncio.retry_if_exception(is_exc)
            ):
                with attempt:
                    attempts += 1
                    if attempts < 3:
                        raise CustomException()

                assert attempt.retry_state.outcome  # help mypy
                if not attempt.retry_state.outcome.failed:
                    attempt.retry_state.set_result(attempts)

            return attempts

        result = await test()

        self.assertEqual(3, result)

    @asynctest
    async def test_retry_with_async_result_or(self) -> None:
        async def test() -> int:
            attempts = 0

            async def lt_3(x: float) -> bool:
                return x < 3

            class CustomException(Exception):
                pass

            def is_exc(e: BaseException) -> bool:
                return isinstance(e, CustomException)

            retry_strategy = tasyncio.retry_if_result(lt_3) | retry_if_exception(is_exc)
            async for attempt in tasyncio.AsyncRetrying(retry=retry_strategy):
                with attempt:
                    attempts += 1
                    if 2 < attempts < 4:
                        raise CustomException()

                assert attempt.retry_state.outcome  # help mypy
                if not attempt.retry_state.outcome.failed:
                    attempt.retry_state.set_result(attempts)

            return attempts

        result = await test()

        self.assertEqual(4, result)

    @asynctest
    async def test_retry_with_async_result_ror(self) -> None:
        async def test() -> int:
            attempts = 0

            def lt_3(x: float) -> bool:
                return x < 3

            class CustomException(Exception):
                pass

            async def is_exc(e: BaseException) -> bool:
                return isinstance(e, CustomException)

            retry_strategy = retry_if_result(lt_3) | tasyncio.retry_if_exception(is_exc)
            async for attempt in tasyncio.AsyncRetrying(retry=retry_strategy):
                with attempt:
                    attempts += 1
                    if 2 < attempts < 4:
                        raise CustomException()

                assert attempt.retry_state.outcome  # help mypy
                if not attempt.retry_state.outcome.failed:
                    attempt.retry_state.set_result(attempts)

            return attempts

        result = await test()

        self.assertEqual(4, result)

    @asynctest
    async def test_retry_with_async_result_and(self) -> None:
        async def test() -> int:
            attempts = 0

            async def lt_3(x: float) -> bool:
                return x < 3

            def gt_0(x: float) -> bool:
                return x > 0

            retry_strategy = tasyncio.retry_if_result(lt_3) & retry_if_result(gt_0)
            async for attempt in tasyncio.AsyncRetrying(retry=retry_strategy):
                with attempt:
                    attempts += 1
                attempt.retry_state.set_result(attempts)

            return attempts

        result = await test()

        self.assertEqual(3, result)

    @asynctest
    async def test_retry_with_async_result_rand(self) -> None:
        async def test() -> int:
            attempts = 0

            async def lt_3(x: float) -> bool:
                return x < 3

            def gt_0(x: float) -> bool:
                return x > 0

            retry_strategy = retry_if_result(gt_0) & tasyncio.retry_if_result(lt_3)
            async for attempt in tasyncio.AsyncRetrying(retry=retry_strategy):
                with attempt:
                    attempts += 1
                attempt.retry_state.set_result(attempts)

            return attempts

        result = await test()

        self.assertEqual(3, result)

    @asynctest
    async def test_async_retying_iterator(self) -> None:
        thing = NoIOErrorAfterCount(5)
        with pytest.raises(TypeError):
            for attempts in AsyncRetrying():
                with attempts:
                    await _async_function(thing)


class TestDecoratorWrapper(unittest.TestCase):
    @asynctest
    async def test_retry_function_attributes(self) -> None:
        """Test that the wrapped function attributes are exposed as intended.

        - statistics contains the value for the latest function run
        - retry object can be modified to change its behaviour (useful to patch in tests)
        - retry object statistics do not contain valid information
        """

        self.assertTrue(
            await _retryable_coroutine_with_2_attempts(NoIOErrorAfterCount(1))
        )

        expected_stats = {
            "attempt_number": 2,
            "delay_since_first_attempt": mock.ANY,
            "idle_for": mock.ANY,
            "start_time": mock.ANY,
        }
        self.assertEqual(
            _retryable_coroutine_with_2_attempts.statistics,
            expected_stats,
        )
        self.assertEqual(
            _retryable_coroutine_with_2_attempts.retry.statistics,
            {},
        )

        with mock.patch.object(
            _retryable_coroutine_with_2_attempts.retry,
            "stop",
            tenacity.stop_after_attempt(1),
        ):
            try:
                self.assertTrue(
                    await _retryable_coroutine_with_2_attempts(NoIOErrorAfterCount(2))
                )
            except RetryError as exc:
                expected_stats = {
                    "attempt_number": 1,
                    "delay_since_first_attempt": mock.ANY,
                    "idle_for": mock.ANY,
                    "start_time": mock.ANY,
                }
                self.assertEqual(
                    _retryable_coroutine_with_2_attempts.statistics,
                    expected_stats,
                )
                self.assertEqual(exc.last_attempt.attempt_number, 1)
                self.assertEqual(
                    _retryable_coroutine_with_2_attempts.retry.statistics,
                    {},
                )
            else:
                self.fail("RetryError should have been raised after 1 attempt")


# make sure mypy accepts passing an async sleep function
# https://github.com/jd/tenacity/issues/399
async def my_async_sleep(x: float) -> None:
    await asyncio.sleep(x)


@retry(sleep=my_async_sleep)
async def foo() -> None:
    pass


class TestSyncFunctionWithAsyncSleep(unittest.TestCase):
    @asynctest
    async def test_sync_function_with_async_sleep(self) -> None:
        """A sync function with an async sleep callable uses AsyncRetrying."""
        mock_sleep = mock.AsyncMock()

        thing = NoneReturnUntilAfterCount(2)

        @retry(
            sleep=mock_sleep,
            wait=wait_fixed(1),
            retry=retry_if_result(lambda x: x is None),
        )
        def sync_function() -> Any:
            return thing.go()

        result = await sync_function()
        assert result is True
        assert mock_sleep.await_count == 2


if __name__ == "__main__":
    unittest.main()
