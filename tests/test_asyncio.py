# mypy: disable-error-code="no-untyped-def,no-untyped-call"
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
from functools import wraps

import pytest

import tenacity
from tenacity import AsyncRetrying, RetryError
from tenacity import _asyncio as tasyncio
from tenacity import retry, retry_if_result, stop_after_attempt
from tenacity.wait import wait_fixed

from .test_tenacity import NoIOErrorAfterCount, current_time_ms


def asynctest(callable_):
    @wraps(callable_)
    def wrapper(*a, **kw):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(callable_(*a, **kw))

    return wrapper


async def _async_function(thing):
    await asyncio.sleep(0.00001)
    return thing.go()


@retry
async def _retryable_coroutine(thing):
    await asyncio.sleep(0.00001)
    return thing.go()


@retry(stop=stop_after_attempt(2))
async def _retryable_coroutine_with_2_attempts(thing):
    await asyncio.sleep(0.00001)
    thing.go()


class TestAsync(unittest.TestCase):
    @asynctest
    async def test_retry(self):
        thing = NoIOErrorAfterCount(5)
        await _retryable_coroutine(thing)
        assert thing.counter == thing.count

    @asynctest
    async def test_iscoroutinefunction(self):
        assert asyncio.iscoroutinefunction(_retryable_coroutine)
        assert inspect.iscoroutinefunction(_retryable_coroutine)

    @asynctest
    async def test_retry_using_async_retying(self):
        thing = NoIOErrorAfterCount(5)
        retrying = AsyncRetrying()
        await retrying(_async_function, thing)
        assert thing.counter == thing.count

    @asynctest
    async def test_stop_after_attempt(self):
        thing = NoIOErrorAfterCount(2)
        try:
            await _retryable_coroutine_with_2_attempts(thing)
        except RetryError:
            assert thing.counter == 2

    def test_repr(self):
        repr(tasyncio.AsyncRetrying())

    def test_retry_attributes(self):
        assert hasattr(_retryable_coroutine, "retry")
        assert hasattr(_retryable_coroutine, "retry_with")

    def test_retry_preserves_argument_defaults(self):
        async def function_with_defaults(a=1):
            return a

        async def function_with_kwdefaults(*, a=1):
            return a

        retrying = AsyncRetrying(wait=tenacity.wait_fixed(0.01), stop=tenacity.stop_after_attempt(3))
        wrapped_defaults_function = retrying.wraps(function_with_defaults)
        wrapped_kwdefaults_function = retrying.wraps(function_with_kwdefaults)

        self.assertEqual(function_with_defaults.__defaults__, wrapped_defaults_function.__defaults__)
        self.assertEqual(function_with_kwdefaults.__kwdefaults__, wrapped_kwdefaults_function.__kwdefaults__)

    @asynctest
    async def test_attempt_number_is_correct_for_interleaved_coroutines(self):
        attempts = []

        def after(retry_state):
            attempts.append((retry_state.args[0], retry_state.attempt_number))

        thing1 = NoIOErrorAfterCount(3)
        thing2 = NoIOErrorAfterCount(3)

        await asyncio.gather(
            _retryable_coroutine.retry_with(after=after)(thing1),  # type: ignore[attr-defined]
            _retryable_coroutine.retry_with(after=after)(thing2),  # type: ignore[attr-defined]
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


class TestContextManager(unittest.TestCase):
    @asynctest
    async def test_do_max_attempts(self):
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
    async def test_reraise(self):
        class CustomError(Exception):
            pass

        try:
            async for attempt in tasyncio.AsyncRetrying(stop=stop_after_attempt(1), reraise=True):
                with attempt:
                    raise CustomError()
        except CustomError:
            pass
        else:
            raise Exception

    @asynctest
    async def test_sleeps(self):
        start = current_time_ms()
        try:
            async for attempt in tasyncio.AsyncRetrying(stop=stop_after_attempt(1), wait=wait_fixed(1)):
                with attempt:
                    raise Exception()
        except RetryError:
            pass
        t = current_time_ms() - start
        self.assertLess(t, 1.1)

    @asynctest
    async def test_retry_with_result(self):
        async def test():
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
    async def test_async_retying_iterator(self):
        thing = NoIOErrorAfterCount(5)
        with pytest.raises(TypeError):
            for attempts in AsyncRetrying():
                with attempts:
                    await _async_function(thing)


# make sure mypy accepts passing an async sleep function
# https://github.com/jd/tenacity/issues/399
async def my_async_sleep(x: float) -> None:
    await asyncio.sleep(x)


@retry(sleep=my_async_sleep)
async def foo():
    pass


if __name__ == "__main__":
    unittest.main()
