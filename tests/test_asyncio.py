# coding: utf-8
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

from tenacity import AsyncRetrying, RetryError
from tenacity import _asyncio as tasyncio
from tenacity import retry, stop_after_attempt
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

    @asynctest
    async def test_attempt_number_is_correct_for_interleaved_coroutines(self):

        attempts = []

        def after(retry_state):
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


if __name__ == "__main__":
    unittest.main()
