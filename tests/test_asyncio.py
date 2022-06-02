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
import logging
import unittest
from functools import wraps

import tenacity
from tenacity import _asyncio as tasyncio
from tenacity import retry, stop_after_attempt
from tenacity.wait import wait_fixed

from .test_tenacity import CapturingHandler, NoIOErrorAfterCount, NoneReturnUntilAfterCount, current_time_ms


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
        retrying = tenacity.AsyncRetrying()
        await retrying(_async_function, thing)
        assert thing.counter == thing.count

    @asynctest
    async def test_stop_after_attempt(self):
        thing = NoIOErrorAfterCount(2)
        try:
            await _retryable_coroutine_with_2_attempts(thing)
        except tenacity.RetryError:
            assert thing.counter == 2

    def test_repr(self):
        repr(tasyncio.AsyncRetrying())

    def test_retry_attributes(self):
        assert hasattr(_retryable_coroutine, "retry")
        assert hasattr(_retryable_coroutine, "retry_with")

    @asynctest
    async def test_async_retry_error_callback_handler(self):
        num_attempts = 3
        self.attempt_counter = 0

        async def _retry_error_callback_handler(retry_state: tenacity.RetryCallState):
            _retry_error_callback_handler.called_times += 1
            return retry_state.outcome

        _retry_error_callback_handler.called_times = 0

        @retry(
            stop=stop_after_attempt(num_attempts),
            retry_error_callback=_retry_error_callback_handler,
        )
        async def _foobar():
            self.attempt_counter += 1
            raise Exception("This exception should not be raised")

        result = await _foobar()

        self.assertEqual(_retry_error_callback_handler.called_times, 1)
        self.assertEqual(num_attempts, self.attempt_counter)
        self.assertIsInstance(result, tenacity.Future)

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
        except tenacity.RetryError:
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
        except tenacity.RetryError:
            pass
        t = current_time_ms() - start
        self.assertLess(t, 1.1)


class TestAsyncBeforeAfterAttempts(unittest.TestCase):
    _attempt_number = 0

    @asynctest
    async def test_before_attempts(self):
        TestAsyncBeforeAfterAttempts._attempt_number = 0

        async def _before(retry_state):
            TestAsyncBeforeAfterAttempts._attempt_number = retry_state.attempt_number

        @retry(
            wait=tenacity.wait_fixed(1),
            stop=tenacity.stop_after_attempt(1),
            before=_before,
        )
        async def _test_before():
            pass

        await _test_before()

        self.assertTrue(TestAsyncBeforeAfterAttempts._attempt_number == 1)

    @asynctest
    async def test_after_attempts(self):
        TestAsyncBeforeAfterAttempts._attempt_number = 0

        async def _after(retry_state):
            TestAsyncBeforeAfterAttempts._attempt_number = retry_state.attempt_number

        @retry(
            wait=tenacity.wait_fixed(0.1),
            stop=tenacity.stop_after_attempt(3),
            after=_after,
        )
        async def _test_after():
            if TestAsyncBeforeAfterAttempts._attempt_number < 2:
                raise Exception("testing after_attempts handler")
            else:
                pass

        await _test_after()

        self.assertTrue(TestAsyncBeforeAfterAttempts._attempt_number == 2)

    @asynctest
    async def test_before_sleep(self):
        async def _before_sleep(retry_state):
            self.assertGreater(retry_state.next_action.sleep, 0)
            _before_sleep.attempt_number = retry_state.attempt_number

        _before_sleep.attempt_number = 0

        @retry(
            wait=tenacity.wait_fixed(0.01),
            stop=tenacity.stop_after_attempt(3),
            before_sleep=_before_sleep,
        )
        async def _test_before_sleep():
            if _before_sleep.attempt_number < 2:
                raise Exception("testing before_sleep_attempts handler")

        await _test_before_sleep()
        self.assertEqual(_before_sleep.attempt_number, 2)

    async def _test_before_sleep_log_returns(self, exc_info):
        thing = NoneReturnUntilAfterCount(2)
        logger = logging.getLogger(self.id())
        logger.propagate = False
        logger.setLevel(logging.INFO)
        handler = CapturingHandler()
        logger.addHandler(handler)
        try:
            _before_sleep = tenacity.before_sleep_log(logger, logging.INFO, exc_info=exc_info)
            _retry = tenacity.retry_if_result(lambda result: result is None)
            retrying = tenacity.AsyncRetrying(
                wait=tenacity.wait_fixed(0.01),
                stop=tenacity.stop_after_attempt(3),
                retry=_retry,
                before_sleep=_before_sleep,
            )
            await retrying(_async_function, thing)
        finally:
            logger.removeHandler(handler)

        etalon_re = r"^Retrying .* in 0\.01 seconds as it returned None\.$"
        self.assertEqual(len(handler.records), 2)
        fmt = logging.Formatter().format
        self.assertRegex(fmt(handler.records[0]), etalon_re)
        self.assertRegex(fmt(handler.records[1]), etalon_re)

    @asynctest
    async def test_before_sleep_log_returns_without_exc_info(self):
        await self._test_before_sleep_log_returns(exc_info=False)

    @asynctest
    async def test_before_sleep_log_returns_with_exc_info(self):
        await self._test_before_sleep_log_returns(exc_info=True)


if __name__ == "__main__":
    unittest.main()
