# Copyright 2016 Julien Danjou
# Copyright 2016 Joshua Harlow
# Copyright 2013 Ray Holder
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
import logging
import time
import unittest
import warnings
from contextlib import contextmanager
from copy import copy

import pytest

import six.moves

import tenacity
from tenacity import RetryError, Retrying, retry
from tenacity.compat import make_retry_state


class TestBase(unittest.TestCase):
    def test_repr(self):
        repr(tenacity.BaseRetrying())


class TestStopConditions(unittest.TestCase):

    def test_never_stop(self):
        r = Retrying()
        self.assertFalse(r.stop(make_retry_state(3, 6546)))

    def test_stop_any(self):
        stop = tenacity.stop_any(
            tenacity.stop_after_delay(1),
            tenacity.stop_after_attempt(4))

        def s(*args):
            return stop(make_retry_state(*args))
        self.assertFalse(s(1, 0.1))
        self.assertFalse(s(2, 0.2))
        self.assertFalse(s(2, 0.8))
        self.assertTrue(s(4, 0.8))
        self.assertTrue(s(3, 1.8))
        self.assertTrue(s(4, 1.8))

    def test_stop_all(self):
        stop = tenacity.stop_all(
            tenacity.stop_after_delay(1),
            tenacity.stop_after_attempt(4))

        def s(*args):
            return stop(make_retry_state(*args))
        self.assertFalse(s(1, 0.1))
        self.assertFalse(s(2, 0.2))
        self.assertFalse(s(2, 0.8))
        self.assertFalse(s(4, 0.8))
        self.assertFalse(s(3, 1.8))
        self.assertTrue(s(4, 1.8))

    def test_stop_or(self):
        stop = tenacity.stop_after_delay(1) | tenacity.stop_after_attempt(4)

        def s(*args):
            return stop(make_retry_state(*args))
        self.assertFalse(s(1, 0.1))
        self.assertFalse(s(2, 0.2))
        self.assertFalse(s(2, 0.8))
        self.assertTrue(s(4, 0.8))
        self.assertTrue(s(3, 1.8))
        self.assertTrue(s(4, 1.8))

    def test_stop_and(self):
        stop = tenacity.stop_after_delay(1) & tenacity.stop_after_attempt(4)

        def s(*args):
            return stop(make_retry_state(*args))
        self.assertFalse(s(1, 0.1))
        self.assertFalse(s(2, 0.2))
        self.assertFalse(s(2, 0.8))
        self.assertFalse(s(4, 0.8))
        self.assertFalse(s(3, 1.8))
        self.assertTrue(s(4, 1.8))

    def test_stop_after_attempt(self):
        r = Retrying(stop=tenacity.stop_after_attempt(3))
        self.assertFalse(r.stop(make_retry_state(2, 6546)))
        self.assertTrue(r.stop(make_retry_state(3, 6546)))
        self.assertTrue(r.stop(make_retry_state(4, 6546)))

    def test_stop_after_delay(self):
        r = Retrying(stop=tenacity.stop_after_delay(1))
        self.assertFalse(r.stop(make_retry_state(2, 0.999)))
        self.assertTrue(r.stop(make_retry_state(2, 1)))
        self.assertTrue(r.stop(make_retry_state(2, 1.001)))

    def test_legacy_explicit_stop_type(self):
        Retrying(stop="stop_after_attempt")

    def test_stop_backward_compat(self):
        r = Retrying(stop=lambda attempt, delay: attempt == delay)
        with reports_deprecation_warning():
            self.assertFalse(r.stop(make_retry_state(1, 3)))
        with reports_deprecation_warning():
            self.assertFalse(r.stop(make_retry_state(100, 99)))
        with reports_deprecation_warning():
            self.assertTrue(r.stop(make_retry_state(101, 101)))

    def test_retry_child_class_with_override_backward_compat(self):

        class MyStop(tenacity.stop_after_attempt):
            def __init__(self):
                super(MyStop, self).__init__(1)

            def __call__(self, attempt_number, seconds_since_start):
                return super(MyStop, self).__call__(
                    attempt_number, seconds_since_start)
        retrying = Retrying(wait=tenacity.wait_fixed(0.01),
                            stop=MyStop())

        def failing():
            raise NotImplementedError()
        with pytest.raises(RetryError):
            retrying.call(failing)

    def test_stop_func_with_retry_state(self):
        def stop_func(retry_state):
            rs = retry_state
            return rs.attempt_number == rs.seconds_since_start

        r = Retrying(stop=stop_func)
        self.assertFalse(r.stop(make_retry_state(1, 3)))
        self.assertFalse(r.stop(make_retry_state(100, 99)))
        self.assertTrue(r.stop(make_retry_state(101, 101)))


class TestWaitConditions(unittest.TestCase):

    def test_no_sleep(self):
        r = Retrying()
        self.assertEqual(0, r.wait(18, 9879))

    def test_fixed_sleep(self):
        r = Retrying(wait=tenacity.wait_fixed(1))
        self.assertEqual(1, r.wait(12, 6546))

    def test_incrementing_sleep(self):
        r = Retrying(wait=tenacity.wait_incrementing(
            start=500, increment=100))
        self.assertEqual(500, r.wait(1, 6546))
        self.assertEqual(600, r.wait(2, 6546))
        self.assertEqual(700, r.wait(3, 6546))

    def test_random_sleep(self):
        r = Retrying(wait=tenacity.wait_random(min=1, max=20))
        times = set()
        for x in six.moves.range(1000):
            times.add(r.wait(1, 6546))

        # this is kind of non-deterministic...
        self.assertTrue(len(times) > 1)
        for t in times:
            self.assertTrue(t >= 1)
            self.assertTrue(t < 20)

    def test_random_sleep_without_min(self):
        r = Retrying(wait=tenacity.wait_random(max=2))
        times = set()
        times.add(r.wait(1, 6546))
        times.add(r.wait(1, 6546))
        times.add(r.wait(1, 6546))
        times.add(r.wait(1, 6546))

        # this is kind of non-deterministic...
        self.assertTrue(len(times) > 1)
        for t in times:
            self.assertTrue(t >= 0)
            self.assertTrue(t <= 2)

    def test_exponential(self):
        r = Retrying(wait=tenacity.wait_exponential(max=100))
        self.assertEqual(r.wait(1, 0), 2)
        self.assertEqual(r.wait(2, 0), 4)
        self.assertEqual(r.wait(3, 0), 8)
        self.assertEqual(r.wait(4, 0), 16)
        self.assertEqual(r.wait(5, 0), 32)
        self.assertEqual(r.wait(6, 0), 64)

    def test_exponential_with_max_wait(self):
        r = Retrying(wait=tenacity.wait_exponential(max=40))
        self.assertEqual(r.wait(1, 0), 2)
        self.assertEqual(r.wait(2, 0), 4)
        self.assertEqual(r.wait(3, 0), 8)
        self.assertEqual(r.wait(4, 0), 16)
        self.assertEqual(r.wait(5, 0), 32)
        self.assertEqual(r.wait(6, 0), 40)
        self.assertEqual(r.wait(7, 0), 40)
        self.assertEqual(r.wait(50, 0), 40)

    def test_exponential_with_min_wait(self):
        r = Retrying(wait=tenacity.wait_exponential(min=20))
        self.assertEqual(r.wait(1, 0), 20)
        self.assertEqual(r.wait(2, 0), 20)
        self.assertEqual(r.wait(3, 0), 20)
        self.assertEqual(r.wait(4, 0), 20)
        self.assertEqual(r.wait(5, 0), 32)
        self.assertEqual(r.wait(6, 0), 64)
        self.assertEqual(r.wait(7, 0), 128)
        self.assertEqual(r.wait(20, 0), 1048576)

    def test_exponential_with_max_wait_and_multiplier(self):
        r = Retrying(wait=tenacity.wait_exponential(
            max=50, multiplier=1))
        self.assertEqual(r.wait(1, 0), 2)
        self.assertEqual(r.wait(2, 0), 4)
        self.assertEqual(r.wait(3, 0), 8)
        self.assertEqual(r.wait(4, 0), 16)
        self.assertEqual(r.wait(5, 0), 32)
        self.assertEqual(r.wait(6, 0), 50)
        self.assertEqual(r.wait(7, 0), 50)
        self.assertEqual(r.wait(50, 0), 50)

    def test_exponential_with_min_wait_and_multiplier(self):
        r = Retrying(wait=tenacity.wait_exponential(
            min=20, multiplier=2))
        self.assertEqual(r.wait(1, 0), 20)
        self.assertEqual(r.wait(2, 0), 20)
        self.assertEqual(r.wait(3, 0), 20)
        self.assertEqual(r.wait(4, 0), 32)
        self.assertEqual(r.wait(5, 0), 64)
        self.assertEqual(r.wait(6, 0), 128)
        self.assertEqual(r.wait(7, 0), 256)
        self.assertEqual(r.wait(20, 0), 2097152)

    def test_exponential_with_min_wait_and_max_wait(self):
        r = Retrying(wait=tenacity.wait_exponential(min=10, max=100))
        self.assertEqual(r.wait(1, 0), 10)
        self.assertEqual(r.wait(2, 0), 10)
        self.assertEqual(r.wait(3, 0), 10)
        self.assertEqual(r.wait(4, 0), 16)
        self.assertEqual(r.wait(5, 0), 32)
        self.assertEqual(r.wait(6, 0), 64)
        self.assertEqual(r.wait(7, 0), 100)
        self.assertEqual(r.wait(20, 0), 100)

    def test_legacy_explicit_wait_type(self):
        Retrying(wait="exponential_sleep")

    def test_wait_backward_compat_with_result(self):
        captures = []

        def wait_capture(attempt, delay, last_result=None):
            captures.append(last_result)
            return 1

        def dying():
            raise Exception("Broken")

        r_attempts = 10
        r = Retrying(wait=wait_capture, sleep=lambda secs: None,
                     stop=tenacity.stop_after_attempt(r_attempts),
                     reraise=True)
        with reports_deprecation_warning():
            self.assertRaises(Exception, r.call, dying)
        self.assertEqual(r_attempts - 1, len(captures))
        self.assertTrue(all([r.failed for r in captures]))

    def test_wait_func(self):
        def wait_func(retry_state):
            return retry_state.attempt_number * retry_state.seconds_since_start
        r = Retrying(wait=wait_func)
        self.assertEqual(r.wait(make_retry_state(1, 5)), 5)
        self.assertEqual(r.wait(make_retry_state(2, 11)), 22)
        self.assertEqual(r.wait(make_retry_state(10, 100)), 1000)

    def test_wait_combine(self):
        r = Retrying(wait=tenacity.wait_combine(tenacity.wait_random(0, 3),
                                                tenacity.wait_fixed(5)))
        # Test it a few time since it's random
        for i in six.moves.range(1000):
            w = r.wait(1, 5)
            self.assertLess(w, 8)
            self.assertGreaterEqual(w, 5)

    def test_wait_double_sum(self):
        r = Retrying(wait=tenacity.wait_random(0, 3) + tenacity.wait_fixed(5))
        # Test it a few time since it's random
        for i in six.moves.range(1000):
            w = r.wait(1, 5)
            self.assertLess(w, 8)
            self.assertGreaterEqual(w, 5)

    def test_wait_triple_sum(self):
        r = Retrying(wait=tenacity.wait_fixed(1) + tenacity.wait_random(0, 3) +
                     tenacity.wait_fixed(5))
        # Test it a few time since it's random
        for i in six.moves.range(1000):
            w = r.wait(1, 5)
            self.assertLess(w, 9)
            self.assertGreaterEqual(w, 6)

    def test_wait_arbitrary_sum(self):
        r = Retrying(wait=sum([tenacity.wait_fixed(1),
                               tenacity.wait_random(0, 3),
                               tenacity.wait_fixed(5),
                               tenacity.wait_none()]))
        # Test it a few time since it's random
        for i in six.moves.range(1000):
            w = r.wait(1, 5)
            self.assertLess(w, 9)
            self.assertGreaterEqual(w, 6)

    def _assert_range(self, wait, min_, max_):
        self.assertLess(wait, max_)
        self.assertGreaterEqual(wait, min_)

    def _assert_inclusive_range(self, wait, low, high):
        self.assertLessEqual(wait, high)
        self.assertGreaterEqual(wait, low)

    def test_wait_chain(self):
        r = Retrying(wait=tenacity.wait_chain(
            *[tenacity.wait_fixed(1) for i in six.moves.range(2)] +
            [tenacity.wait_fixed(4) for i in six.moves.range(2)] +
            [tenacity.wait_fixed(8) for i in six.moves.range(1)]))

        for i in six.moves.range(10):
            w = r.wait(i + 1, 1)
            if i < 2:
                self._assert_range(w, 1, 2)
            elif i < 4:
                self._assert_range(w, 4, 5)
            else:
                self._assert_range(w, 8, 9)

    def test_wait_chain_multiple_invocations(self):
        sleep_intervals = []
        r = Retrying(
            sleep=sleep_intervals.append,
            wait=tenacity.wait_chain(*[
                tenacity.wait_fixed(i + 1) for i in six.moves.range(3)
            ]),
            stop=tenacity.stop_after_attempt(5),
            retry=tenacity.retry_if_result(lambda x: x == 1),
        )

        @r.wraps
        def always_return_1():
            return 1

        self.assertRaises(tenacity.RetryError, always_return_1)
        self.assertEqual(sleep_intervals, [1.0, 2.0, 3.0, 3.0])
        sleep_intervals[:] = []

        # Clear and restart retrying.
        self.assertRaises(tenacity.RetryError, always_return_1)
        self.assertEqual(sleep_intervals, [1.0, 2.0, 3.0, 3.0])
        sleep_intervals[:] = []

    def test_wait_random_exponential(self):
        fn = tenacity.wait_random_exponential(0.5, 60.0)

        for _ in six.moves.range(1000):
            self._assert_inclusive_range(fn(0, 0), 0, 0.5)
            self._assert_inclusive_range(fn(1, 0), 0, 1.0)
            self._assert_inclusive_range(fn(2, 0), 0, 2.0)
            self._assert_inclusive_range(fn(3, 0), 0, 4.0)
            self._assert_inclusive_range(fn(4, 0), 0, 8.0)
            self._assert_inclusive_range(fn(5, 0), 0, 16.0)
            self._assert_inclusive_range(fn(6, 0), 0, 32.0)
            self._assert_inclusive_range(fn(7, 0), 0, 60.0)
            self._assert_inclusive_range(fn(8, 0), 0, 60.0)
            self._assert_inclusive_range(fn(9, 0), 0, 60.0)

        fn = tenacity.wait_random_exponential(10, 5)
        for _ in six.moves.range(1000):
            self._assert_inclusive_range(fn(0, 0), 0.00, 5.00)

        # Default arguments exist
        fn = tenacity.wait_random_exponential()
        fn(0, 0)

    def test_wait_random_exponential_statistically(self):
        fn = tenacity.wait_random_exponential(0.5, 60.0)

        attempt = []
        for i in six.moves.range(10):
            attempt.append(
                [fn(i, 0) for _ in six.moves.range(4000)]
            )

        def mean(lst):
            return float(sum(lst)) / float(len(lst))

        self._assert_inclusive_range(mean(attempt[0]), 0.20, 0.30)
        self._assert_inclusive_range(mean(attempt[1]), 0.35, 0.65)
        self._assert_inclusive_range(mean(attempt[2]), 0.75, 1.25)
        self._assert_inclusive_range(mean(attempt[3]), 1.75, 3.25)
        self._assert_inclusive_range(mean(attempt[4]), 3.50, 5.50)
        self._assert_inclusive_range(mean(attempt[5]), 7.00, 9.00)
        self._assert_inclusive_range(mean(attempt[6]), 14.00, 18.00)
        self._assert_inclusive_range(mean(attempt[7]), 28.00, 34.00)
        self._assert_inclusive_range(mean(attempt[8]), 28.00, 34.00)
        self._assert_inclusive_range(mean(attempt[9]), 28.00, 34.00)

    def test_wait_backward_compat(self):
        """Ensure Retrying object accepts both old and newstyle wait funcs."""
        def wait1(previous_attempt_number, delay_since_first_attempt):
            wait1.calls.append((
                previous_attempt_number, delay_since_first_attempt))
            return 0
        wait1.calls = []

        def wait2(previous_attempt_number, delay_since_first_attempt,
                  last_result):
            wait2.calls.append((
                previous_attempt_number, delay_since_first_attempt,
                last_result))
            return 0
        wait2.calls = []

        def dying():
            raise Exception("Broken")

        retrying1 = Retrying(wait=wait1, stop=tenacity.stop_after_attempt(4))
        with reports_deprecation_warning():
            self.assertRaises(Exception, lambda: retrying1.call(dying))
        self.assertEqual([t[0] for t in wait1.calls], [1, 2, 3])
        # This assumes that 3 iterations complete within 1 second.
        self.assertTrue(all(t[1] < 1 for t in wait1.calls))

        retrying2 = Retrying(wait=wait2, stop=tenacity.stop_after_attempt(4))
        with reports_deprecation_warning():
            self.assertRaises(Exception, lambda: retrying2.call(dying))
        self.assertEqual([t[0] for t in wait2.calls], [1, 2, 3])
        # This assumes that 3 iterations complete within 1 second.
        self.assertTrue(all(t[1] < 1 for t in wait2.calls))
        self.assertEqual([str(t[2].exception()) for t in wait2.calls],
                         ['Broken'] * 3)

    def test_wait_class_backward_compatibility(self):
        """Ensure builtin objects accept both old and new parameters."""
        waitobj = tenacity.wait_fixed(5)
        self.assertEqual(waitobj(1, 0.1), 5)
        self.assertEqual(
            waitobj(1, 0.1, tenacity.Future.construct(1, 1, False)), 5)
        retry_state = make_retry_state(123, 456)
        self.assertEqual(retry_state.attempt_number, 123)
        self.assertEqual(retry_state.seconds_since_start, 456)
        self.assertEqual(waitobj(retry_state=retry_state), 5)

    def test_wait_retry_state_attributes(self):

        class ExtractCallState(Exception):
            pass

        # retry_state is mutable, so return it as an exception to extract the
        # exact values it has when wait is called and bypass any other logic.
        def waitfunc(retry_state):
            raise ExtractCallState(retry_state)

        retrying = Retrying(
            wait=waitfunc,
            retry=(tenacity.retry_if_exception_type() |
                   tenacity.retry_if_result(lambda result: result == 123)))

        def returnval():
            return 123
        try:
            retrying.call(returnval)
        except ExtractCallState as err:
            retry_state = err.args[0]
        self.assertIs(retry_state.fn, returnval)
        self.assertEqual(retry_state.args, ())
        self.assertEqual(retry_state.kwargs, {})
        self.assertEqual(retry_state.outcome.result(), 123)
        self.assertEqual(retry_state.attempt_number, 1)
        self.assertGreater(retry_state.outcome_timestamp,
                           retry_state.start_time)

        def dying():
            raise Exception("Broken")
        try:
            retrying.call(dying)
        except ExtractCallState as err:
            retry_state = err.args[0]
        self.assertIs(retry_state.fn, dying)
        self.assertEqual(retry_state.args, ())
        self.assertEqual(retry_state.kwargs, {})
        self.assertEqual(str(retry_state.outcome.exception()), 'Broken')
        self.assertEqual(retry_state.attempt_number, 1)
        self.assertGreater(retry_state.outcome_timestamp,
                           retry_state.start_time)


class TestRetryConditions(unittest.TestCase):

    def test_retry_if_result(self):
        retry = (tenacity.retry_if_result(lambda x: x == 1))

        def r(fut):
            retry_state = make_retry_state(1, 1.0, last_result=fut)
            return retry(retry_state)
        self.assertTrue(r(tenacity.Future.construct(1, 1, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 2, False)))

    def test_retry_if_not_result(self):
        retry = (tenacity.retry_if_not_result(lambda x: x == 1))

        def r(fut):
            retry_state = make_retry_state(1, 1.0, last_result=fut)
            return retry(retry_state)
        self.assertTrue(r(tenacity.Future.construct(1, 2, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 1, False)))

    def test_retry_any(self):
        retry = tenacity.retry_any(
            tenacity.retry_if_result(lambda x: x == 1),
            tenacity.retry_if_result(lambda x: x == 2))

        def r(fut):
            retry_state = make_retry_state(1, 1.0, last_result=fut)
            return retry(retry_state)
        self.assertTrue(r(tenacity.Future.construct(1, 1, False)))
        self.assertTrue(r(tenacity.Future.construct(1, 2, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 3, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 1, True)))

    def test_retry_all(self):
        retry = tenacity.retry_all(
            tenacity.retry_if_result(lambda x: x == 1),
            tenacity.retry_if_result(lambda x: isinstance(x, int)))

        def r(fut):
            retry_state = make_retry_state(1, 1.0, last_result=fut)
            return retry(retry_state)
        self.assertTrue(r(tenacity.Future.construct(1, 1, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 2, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 3, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 1, True)))

    def test_retry_and(self):
        retry = (tenacity.retry_if_result(lambda x: x == 1) &
                 tenacity.retry_if_result(lambda x: isinstance(x, int)))

        def r(fut):
            retry_state = make_retry_state(1, 1.0, last_result=fut)
            return retry(retry_state)
        self.assertTrue(r(tenacity.Future.construct(1, 1, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 2, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 3, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 1, True)))

    def test_retry_or(self):
        retry = (tenacity.retry_if_result(lambda x: x == "foo") |
                 tenacity.retry_if_result(lambda x: isinstance(x, int)))

        def r(fut):
            retry_state = make_retry_state(1, 1.0, last_result=fut)
            return retry(retry_state)
        self.assertTrue(r(tenacity.Future.construct(1, "foo", False)))
        self.assertFalse(r(tenacity.Future.construct(1, "foobar", False)))
        self.assertFalse(r(tenacity.Future.construct(1, 2.2, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 42, True)))

    def _raise_try_again(self):
        self._attempts += 1
        if self._attempts < 3:
            raise tenacity.TryAgain

    def test_retry_try_again(self):
        self._attempts = 0
        Retrying(stop=tenacity.stop_after_attempt(5),
                 retry=tenacity.retry_never).call(self._raise_try_again)
        self.assertEqual(3, self._attempts)

    def test_retry_try_again_forever(self):
        def _r():
            raise tenacity.TryAgain

        r = Retrying(stop=tenacity.stop_after_attempt(5),
                     retry=tenacity.retry_never)
        self.assertRaises(tenacity.RetryError,
                          r.call,
                          _r)
        self.assertEqual(5, r.statistics['attempt_number'])

    def test_retry_try_again_forever_reraise(self):
        def _r():
            raise tenacity.TryAgain

        r = Retrying(stop=tenacity.stop_after_attempt(5),
                     retry=tenacity.retry_never,
                     reraise=True)
        self.assertRaises(tenacity.TryAgain,
                          r,
                          _r)
        self.assertEqual(5, r.statistics['attempt_number'])

    def test_retry_if_exception_message_negative_no_inputs(self):
        with self.assertRaises(TypeError):
            tenacity.retry_if_exception_message()

    def test_retry_if_exception_message_negative_too_many_inputs(self):
        with self.assertRaises(TypeError):
            tenacity.retry_if_exception_message(
                message="negative", match="negative")


class NoneReturnUntilAfterCount(object):
    """Holds counter state for invoking a method several times in a row."""

    def __init__(self, count):
        self.counter = 0
        self.count = count

    def go(self):
        """Return None until after count threshold has been crossed.

        Then return True.
        """
        if self.counter < self.count:
            self.counter += 1
            return None
        return True


class NoIOErrorAfterCount(object):
    """Holds counter state for invoking a method several times in a row."""

    def __init__(self, count):
        self.counter = 0
        self.count = count

    def go(self):
        """Raise an IOError until after count threshold has been crossed.

        Then return True.
        """
        if self.counter < self.count:
            self.counter += 1
            raise IOError("Hi there, I'm an IOError")
        return True


class NoNameErrorAfterCount(object):
    """Holds counter state for invoking a method several times in a row."""

    def __init__(self, count):
        self.counter = 0
        self.count = count

    def go(self):
        """Raise a NameError until after count threshold has been crossed.

        Then return True.
        """
        if self.counter < self.count:
            self.counter += 1
            raise NameError("Hi there, I'm a NameError")
        return True


class NameErrorUntilCount(object):
    """Holds counter state for invoking a method several times in a row."""

    derived_message = "Hi there, I'm a NameError"

    def __init__(self, count):
        self.counter = 0
        self.count = count

    def go(self):
        """Return True until after count threshold has been crossed.

        Then raise a NameError.
        """
        if self.counter < self.count:
            self.counter += 1
            return True
        raise NameError(self.derived_message)


class IOErrorUntilCount(object):
    """Holds counter state for invoking a method several times in a row."""

    def __init__(self, count):
        self.counter = 0
        self.count = count

    def go(self):
        """Return True until after count threshold has been crossed.

        Then raise an IOError.
        """
        if self.counter < self.count:
            self.counter += 1
            return True
        raise IOError("Hi there, I'm an IOError")


class CustomError(Exception):
    """This is a custom exception class.

    Note that For Python 2.x, we don't strictly need to extend BaseException,
    however, Python 3.x will complain. While this test suite won't run
    correctly under Python 3.x without extending from the Python exception
    hierarchy, the actual module code is backwards compatible Python 2.x and
    will allow for cases where exception classes don't extend from the
    hierarchy.
    """

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value


class NoCustomErrorAfterCount(object):
    """Holds counter state for invoking a method several times in a row."""

    derived_message = "This is a Custom exception class"

    def __init__(self, count):
        self.counter = 0
        self.count = count

    def go(self):
        """Raise a CustomError until after count threshold has been crossed.

        Then return True.
        """
        if self.counter < self.count:
            self.counter += 1
            raise CustomError(self.derived_message)
        return True


class CapturingHandler(logging.Handler):
    """Captures log records for inspection."""

    def __init__(self, *args, **kwargs):
        super(CapturingHandler, self).__init__(*args, **kwargs)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def current_time_ms():
    return int(round(time.time() * 1000))


@retry(wait=tenacity.wait_fixed(0.05),
       retry=tenacity.retry_if_result(lambda result: result is None))
def _retryable_test_with_wait(thing):
    return thing.go()


@retry(stop=tenacity.stop_after_attempt(3),
       retry=tenacity.retry_if_result(lambda result: result is None))
def _retryable_test_with_stop(thing):
    return thing.go()


@retry(retry=tenacity.retry_if_exception_type(IOError))
def _retryable_test_with_exception_type_io(thing):
    return thing.go()


@retry(
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_if_exception_type(IOError))
def _retryable_test_with_exception_type_io_attempt_limit(thing):
    return thing.go()


@retry(retry=tenacity.retry_unless_exception_type(NameError))
def _retryable_test_with_unless_exception_type_name(thing):
    return thing.go()


@retry(
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_unless_exception_type(NameError))
def _retryable_test_with_unless_exception_type_name_attempt_limit(thing):
    return thing.go()


@retry(retry=tenacity.retry_unless_exception_type())
def _retryable_test_with_unless_exception_type_no_input(thing):
    return thing.go()


@retry(
    stop=tenacity.stop_after_attempt(5),
    retry=tenacity.retry_if_exception_message(
        message=NoCustomErrorAfterCount.derived_message))
def _retryable_test_if_exception_message_message(thing):
    return thing.go()


@retry(retry=tenacity.retry_if_not_exception_message(
    message=NoCustomErrorAfterCount.derived_message))
def _retryable_test_if_not_exception_message_message(thing):
    return thing.go()


@retry(retry=tenacity.retry_if_exception_message(
    match=NoCustomErrorAfterCount.derived_message[:3] + ".*"))
def _retryable_test_if_exception_message_match(thing):
    return thing.go()


@retry(retry=tenacity.retry_if_not_exception_message(
    match=NoCustomErrorAfterCount.derived_message[:3] + ".*"))
def _retryable_test_if_not_exception_message_match(thing):
    return thing.go()


@retry(retry=tenacity.retry_if_not_exception_message(
    message=NameErrorUntilCount.derived_message))
def _retryable_test_not_exception_message_delay(thing):
    return thing.go()


@retry
def _retryable_default(thing):
    return thing.go()


@retry()
def _retryable_default_f(thing):
    return thing.go()


@retry(retry=tenacity.retry_if_exception_type(CustomError))
def _retryable_test_with_exception_type_custom(thing):
    return thing.go()


@retry(
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_if_exception_type(CustomError))
def _retryable_test_with_exception_type_custom_attempt_limit(thing):
    return thing.go()


class TestDecoratorWrapper(unittest.TestCase):

    def test_with_wait(self):
        start = current_time_ms()
        result = _retryable_test_with_wait(NoneReturnUntilAfterCount(5))
        t = current_time_ms() - start
        self.assertGreaterEqual(t, 250)
        self.assertTrue(result)

    def test_retry_with(self):
        start = current_time_ms()
        result = _retryable_test_with_wait.retry_with(
            wait=tenacity.wait_fixed(0.1))(NoneReturnUntilAfterCount(5))
        t = current_time_ms() - start
        self.assertGreaterEqual(t, 500)
        self.assertTrue(result)

    def test_with_stop_on_return_value(self):
        try:
            _retryable_test_with_stop(NoneReturnUntilAfterCount(5))
            self.fail("Expected RetryError after 3 attempts")
        except RetryError as re:
            self.assertFalse(re.last_attempt.failed)
            self.assertEqual(3, re.last_attempt.attempt_number)
            self.assertTrue(re.last_attempt.result() is None)
            print(re)

    def test_with_stop_on_exception(self):
        try:
            _retryable_test_with_stop(NoIOErrorAfterCount(5))
            self.fail("Expected IOError")
        except IOError as re:
            self.assertTrue(isinstance(re, IOError))
            print(re)

    def test_retry_if_exception_of_type(self):
        self.assertTrue(_retryable_test_with_exception_type_io(
            NoIOErrorAfterCount(5)))

        try:
            _retryable_test_with_exception_type_io(NoNameErrorAfterCount(5))
            self.fail("Expected NameError")
        except NameError as n:
            self.assertTrue(isinstance(n, NameError))
            print(n)

        self.assertTrue(_retryable_test_with_exception_type_custom(
            NoCustomErrorAfterCount(5)))

        try:
            _retryable_test_with_exception_type_custom(
                NoNameErrorAfterCount(5))
            self.fail("Expected NameError")
        except NameError as n:
            self.assertTrue(isinstance(n, NameError))
            print(n)

    def test_retry_until_exception_of_type_attempt_number(self):
        try:
            self.assertTrue(_retryable_test_with_unless_exception_type_name(
                NameErrorUntilCount(5)))
        except NameError as e:
            s = _retryable_test_with_unless_exception_type_name.\
                retry.statistics
            self.assertTrue(s['attempt_number'] == 6)
            print(e)
        else:
            self.fail("Expected NameError")

    def test_retry_until_exception_of_type_no_type(self):
        try:
            # no input should catch all subclasses of Exception
            self.assertTrue(
                _retryable_test_with_unless_exception_type_no_input(
                    NameErrorUntilCount(5))
            )
        except NameError as e:
            s = _retryable_test_with_unless_exception_type_no_input.\
                retry.statistics
            self.assertTrue(s['attempt_number'] == 6)
            print(e)
        else:
            self.fail("Expected NameError")

    def test_retry_until_exception_of_type_wrong_exception(self):
        try:
            # two iterations with IOError, one that returns True
            _retryable_test_with_unless_exception_type_name_attempt_limit(
                IOErrorUntilCount(2))
            self.fail("Expected RetryError")
        except RetryError as e:
            self.assertTrue(isinstance(e, RetryError))
            print(e)

    def test_retry_if_exception_message(self):
        try:
            self.assertTrue(_retryable_test_if_exception_message_message(
                NoCustomErrorAfterCount(3)))
        except CustomError:
            print(_retryable_test_if_exception_message_message.retry.
                  statistics)
            self.fail("CustomError should've been retried from errormessage")

    def test_retry_if_not_exception_message(self):
        try:
            self.assertTrue(_retryable_test_if_not_exception_message_message(
                NoCustomErrorAfterCount(2)))
        except CustomError:
            s = _retryable_test_if_not_exception_message_message.retry.\
                statistics
            self.assertTrue(s['attempt_number'] == 1)

    def test_retry_if_not_exception_message_delay(self):
        try:
            self.assertTrue(_retryable_test_not_exception_message_delay(
                NameErrorUntilCount(3)))
        except NameError:
            s = _retryable_test_not_exception_message_delay.retry.statistics
            print(s['attempt_number'])
            self.assertTrue(s['attempt_number'] == 4)

    def test_retry_if_exception_message_match(self):
        try:
            self.assertTrue(_retryable_test_if_exception_message_match(
                NoCustomErrorAfterCount(3)))
        except CustomError:
            self.fail("CustomError should've been retried from errormessage")

    def test_retry_if_not_exception_message_match(self):
        try:
            self.assertTrue(_retryable_test_if_not_exception_message_message(
                NoCustomErrorAfterCount(2)))
        except CustomError:
            s = _retryable_test_if_not_exception_message_message.retry.\
                statistics
            self.assertTrue(s['attempt_number'] == 1)

    def test_defaults(self):
        self.assertTrue(_retryable_default(NoNameErrorAfterCount(5)))
        self.assertTrue(_retryable_default_f(NoNameErrorAfterCount(5)))
        self.assertTrue(_retryable_default(NoCustomErrorAfterCount(5)))
        self.assertTrue(_retryable_default_f(NoCustomErrorAfterCount(5)))

    def test_retry_function_object(self):
        """Test that six.wraps doesn't cause problems with callable objects.

        It raises an error upon trying to wrap it in Py2, because __name__
        attribute is missing. It's fixed in Py3 but was never backported.
        """
        class Hello(object):
            def __call__(self):
                return "Hello"
        retrying = Retrying(wait=tenacity.wait_fixed(0.01),
                            stop=tenacity.stop_after_attempt(3))
        h = retrying.wraps(Hello())
        self.assertEqual(h(), "Hello")

    def test_retry_child_class_with_override_backward_compat(self):
        def always_true(_):
            return True

        class MyRetry(tenacity.retry_if_exception):
            def __init__(self):
                super(MyRetry, self).__init__(always_true)

            def __call__(self, attempt):
                return super(MyRetry, self).__call__(attempt)
        retrying = Retrying(wait=tenacity.wait_fixed(0.01),
                            stop=tenacity.stop_after_attempt(1),
                            retry=MyRetry())

        def failing():
            raise NotImplementedError()
        with pytest.raises(RetryError):
            retrying.call(failing)


class TestBeforeAfterAttempts(unittest.TestCase):
    _attempt_number = 0

    def test_before_attempts(self):
        TestBeforeAfterAttempts._attempt_number = 0

        def _before(retry_state):
            TestBeforeAfterAttempts._attempt_number = \
                retry_state.attempt_number

        @retry(wait=tenacity.wait_fixed(1),
               stop=tenacity.stop_after_attempt(1),
               before=_before)
        def _test_before():
            pass

        _test_before()

        self.assertTrue(TestBeforeAfterAttempts._attempt_number is 1)

    def test_after_attempts(self):
        TestBeforeAfterAttempts._attempt_number = 0

        def _after(retry_state):
            TestBeforeAfterAttempts._attempt_number = \
                retry_state.attempt_number

        @retry(wait=tenacity.wait_fixed(0.1),
               stop=tenacity.stop_after_attempt(3),
               after=_after)
        def _test_after():
            if TestBeforeAfterAttempts._attempt_number < 2:
                raise Exception("testing after_attempts handler")
            else:
                pass

        _test_after()

        self.assertTrue(TestBeforeAfterAttempts._attempt_number is 2)

    def test_before_sleep(self):
        def _before_sleep(retry_state):
            self.assertGreater(retry_state.next_action.sleep, 0)
            _before_sleep.attempt_number = retry_state.attempt_number

        @retry(wait=tenacity.wait_fixed(0.01),
               stop=tenacity.stop_after_attempt(3),
               before_sleep=_before_sleep)
        def _test_before_sleep():
            if _before_sleep.attempt_number < 2:
                raise Exception("testing before_sleep_attempts handler")

        _test_before_sleep()
        self.assertEqual(_before_sleep.attempt_number, 2)

    def test_before_sleep_backward_compat(self):
        def _before_sleep(retry_obj, sleep, last_result):
            self.assertGreater(sleep, 0)
            _before_sleep.attempt_number = \
                retry_obj.statistics['attempt_number']
        _before_sleep.attempt_number = 0

        @retry(wait=tenacity.wait_fixed(0.01),
               stop=tenacity.stop_after_attempt(3),
               before_sleep=_before_sleep)
        def _test_before_sleep():
            if _before_sleep.attempt_number < 2:
                raise Exception("testing before_sleep_attempts handler")

        with reports_deprecation_warning():
            _test_before_sleep()
        self.assertEqual(_before_sleep.attempt_number, 2)

    def test_before_sleep_log_raises(self):
        thing = NoIOErrorAfterCount(2)
        logger = logging.getLogger(self.id())
        logger.propagate = False
        logger.setLevel(logging.INFO)
        handler = CapturingHandler()
        logger.addHandler(handler)
        try:
            _before_sleep = tenacity.before_sleep_log(logger, logging.INFO)
            retrying = Retrying(wait=tenacity.wait_fixed(0.01),
                                stop=tenacity.stop_after_attempt(3),
                                before_sleep=_before_sleep)
            retrying.call(thing.go)
        finally:
            logger.removeHandler(handler)

        etalon_re = r'Retrying .* in 0\.01 seconds as it raised .*\.'
        self.assertEqual(len(handler.records), 2)
        self.assertRegexpMatches(handler.records[0].getMessage(), etalon_re)
        self.assertRegexpMatches(handler.records[1].getMessage(), etalon_re)

    def test_before_sleep_log_returns(self):
        thing = NoneReturnUntilAfterCount(2)
        logger = logging.getLogger(self.id())
        logger.propagate = False
        logger.setLevel(logging.INFO)
        handler = CapturingHandler()
        logger.addHandler(handler)
        try:
            _before_sleep = tenacity.before_sleep_log(logger, logging.INFO)
            _retry = tenacity.retry_if_result(lambda result: result is None)
            retrying = Retrying(wait=tenacity.wait_fixed(0.01),
                                stop=tenacity.stop_after_attempt(3),
                                retry=_retry, before_sleep=_before_sleep)
            retrying.call(thing.go)
        finally:
            logger.removeHandler(handler)

        self.assertEqual(len(handler.records), 2)
        etalon_re = r'Retrying .* in 0\.01 seconds as it returned None'
        self.assertRegexpMatches(handler.records[0].getMessage(), etalon_re)
        self.assertRegexpMatches(handler.records[1].getMessage(), etalon_re)


class TestReraiseExceptions(unittest.TestCase):

    def test_reraise_by_default(self):
        calls = []

        @retry(wait=tenacity.wait_fixed(0.1),
               stop=tenacity.stop_after_attempt(2),
               reraise=True)
        def _reraised_by_default():
            calls.append('x')
            raise KeyError("Bad key")

        self.assertRaises(KeyError, _reraised_by_default)
        self.assertEqual(2, len(calls))

    def test_reraise_from_retry_error(self):
        calls = []

        @retry(wait=tenacity.wait_fixed(0.1),
               stop=tenacity.stop_after_attempt(2))
        def _raise_key_error():
            calls.append('x')
            raise KeyError("Bad key")

        def _reraised_key_error():
            try:
                _raise_key_error()
            except tenacity.RetryError as retry_err:
                retry_err.reraise()

        self.assertRaises(KeyError, _reraised_key_error)
        self.assertEqual(2, len(calls))

    def test_reraise_timeout_from_retry_error(self):
        calls = []

        @retry(wait=tenacity.wait_fixed(0.1),
               stop=tenacity.stop_after_attempt(2),
               retry=lambda retry_state: True)
        def _mock_fn():
            calls.append('x')

        def _reraised_mock_fn():
            try:
                _mock_fn()
            except tenacity.RetryError as retry_err:
                retry_err.reraise()

        self.assertRaises(tenacity.RetryError, _reraised_mock_fn)
        self.assertEqual(2, len(calls))

    def test_reraise_no_exception(self):
        calls = []

        @retry(wait=tenacity.wait_fixed(0.1),
               stop=tenacity.stop_after_attempt(2),
               retry=lambda retry_state: True,
               reraise=True)
        def _mock_fn():
            calls.append('x')

        self.assertRaises(tenacity.RetryError, _mock_fn)
        self.assertEqual(2, len(calls))


class TestStatistics(unittest.TestCase):

    def test_stats(self):
        @retry()
        def _foobar():
            return 42

        self.assertEqual({}, _foobar.retry.statistics)
        _foobar()
        self.assertEqual(1, _foobar.retry.statistics['attempt_number'])

    def test_stats_failing(self):
        @retry(stop=tenacity.stop_after_attempt(2))
        def _foobar():
            raise ValueError(42)

        self.assertEqual({}, _foobar.retry.statistics)
        try:
            _foobar()
        except Exception:
            pass
        self.assertEqual(2, _foobar.retry.statistics['attempt_number'])


class TestRetryErrorCallback(unittest.TestCase):

    def setUp(self):
        self._attempt_number = 0
        self._callback_called = False

    def _callback(self, fut):
        self._callback_called = True
        return fut

    def test_retry_error_callback_backward_compat(self):
        num_attempts = 3

        def retry_error_callback(fut):
            retry_error_callback.called_times += 1
            return fut

        retry_error_callback.called_times = 0

        @retry(stop=tenacity.stop_after_attempt(num_attempts),
               retry_error_callback=retry_error_callback)
        def _foobar():
            self._attempt_number += 1
            raise Exception("This exception should not be raised")

        with reports_deprecation_warning():
            result = _foobar()

        self.assertEqual(retry_error_callback.called_times, 1)
        self.assertEqual(num_attempts, self._attempt_number)
        self.assertIsInstance(result, tenacity.Future)

    def test_retry_error_callback(self):
        num_attempts = 3

        def retry_error_callback(retry_state):
            retry_error_callback.called_times += 1
            return retry_state.outcome

        retry_error_callback.called_times = 0

        @retry(stop=tenacity.stop_after_attempt(num_attempts),
               retry_error_callback=retry_error_callback)
        def _foobar():
            self._attempt_number += 1
            raise Exception("This exception should not be raised")

        result = _foobar()

        self.assertEqual(retry_error_callback.called_times, 1)
        self.assertEqual(num_attempts, self._attempt_number)
        self.assertIsInstance(result, tenacity.Future)


@contextmanager
def reports_deprecation_warning():
    __tracebackhide__ = True
    oldfilters = copy(warnings.filters)
    warnings.simplefilter('always')
    try:
        with pytest.warns(DeprecationWarning):
            yield
    finally:
        warnings.filters = oldfilters


if __name__ == '__main__':
    unittest.main()
