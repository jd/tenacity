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
import time
import unittest

import six.moves

import tenacity
from tenacity import RetryError
from tenacity import Retrying
from tenacity import retry


class TestBase(unittest.TestCase):
    def test_repr(self):
        repr(tenacity.BaseRetrying())


class TestStopConditions(unittest.TestCase):

    def test_never_stop(self):
        r = Retrying()
        self.assertFalse(r.stop(3, 6546))

    def test_stop_any(self):
        s = tenacity.stop_any(
            tenacity.stop_after_delay(1),
            tenacity.stop_after_attempt(4))
        self.assertFalse(s(1, 0.1))
        self.assertFalse(s(2, 0.2))
        self.assertFalse(s(2, 0.8))
        self.assertTrue(s(4, 0.8))
        self.assertTrue(s(3, 1.8))
        self.assertTrue(s(4, 1.8))

    def test_stop_all(self):
        s = tenacity.stop_all(
            tenacity.stop_after_delay(1),
            tenacity.stop_after_attempt(4))
        self.assertFalse(s(1, 0.1))
        self.assertFalse(s(2, 0.2))
        self.assertFalse(s(2, 0.8))
        self.assertFalse(s(4, 0.8))
        self.assertFalse(s(3, 1.8))
        self.assertTrue(s(4, 1.8))

    def test_stop_or(self):
        s = tenacity.stop_after_delay(1) | tenacity.stop_after_attempt(4)
        self.assertFalse(s(1, 0.1))
        self.assertFalse(s(2, 0.2))
        self.assertFalse(s(2, 0.8))
        self.assertTrue(s(4, 0.8))
        self.assertTrue(s(3, 1.8))
        self.assertTrue(s(4, 1.8))

    def test_stop_and(self):
        s = tenacity.stop_after_delay(1) & tenacity.stop_after_attempt(4)
        self.assertFalse(s(1, 0.1))
        self.assertFalse(s(2, 0.2))
        self.assertFalse(s(2, 0.8))
        self.assertFalse(s(4, 0.8))
        self.assertFalse(s(3, 1.8))
        self.assertTrue(s(4, 1.8))

    def test_stop_after_attempt(self):
        r = Retrying(stop=tenacity.stop_after_attempt(3))
        self.assertFalse(r.stop(2, 6546))
        self.assertTrue(r.stop(3, 6546))
        self.assertTrue(r.stop(4, 6546))

    def test_stop_after_delay(self):
        r = Retrying(stop=tenacity.stop_after_delay(1))
        self.assertFalse(r.stop(2, 0.999))
        self.assertTrue(r.stop(2, 1))
        self.assertTrue(r.stop(2, 1.001))

    def test_legacy_explicit_stop_type(self):
        Retrying(stop="stop_after_attempt")

    def test_stop_func(self):
        r = Retrying(stop=lambda attempt, delay: attempt == delay)
        self.assertFalse(r.stop(1, 3))
        self.assertFalse(r.stop(100, 99))
        self.assertTrue(r.stop(101, 101))


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

    def test_legacy_explicit_wait_type(self):
        Retrying(wait="exponential_sleep")

    def test_wait_func_result(self):
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
        self.assertRaises(Exception, r.call, dying)
        self.assertEqual(r_attempts - 1, len(captures))
        self.assertTrue(all([r.failed for r in captures]))

    def test_wait_func(self):
        r = Retrying(wait=lambda attempt, delay: attempt * delay)
        self.assertEqual(r.wait(1, 5), 5)
        self.assertEqual(r.wait(2, 11), 22)
        self.assertEqual(r.wait(10, 100), 1000)

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
            w = r.wait(i, 1)
            if i < 2:
                self._assert_range(w, 1, 2)
            elif i < 4:
                self._assert_range(w, 4, 5)
            else:
                self._assert_range(w, 8, 9)

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


class TestRetryConditions(unittest.TestCase):

    def test_retry_if_result(self):
        r = (tenacity.retry_if_result(lambda x: x == 1))
        self.assertTrue(r(tenacity.Future.construct(1, 1, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 2, False)))

    def test_retry_if_not_result(self):
        r = (tenacity.retry_if_not_result(lambda x: x == 1))
        self.assertTrue(r(tenacity.Future.construct(1, 2, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 1, False)))

    def test_retry_any(self):
        r = tenacity.retry_any(
            tenacity.retry_if_result(lambda x: x == 1),
            tenacity.retry_if_result(lambda x: x == 2))
        self.assertTrue(r(tenacity.Future.construct(1, 1, False)))
        self.assertTrue(r(tenacity.Future.construct(1, 2, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 3, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 1, True)))

    def test_retry_all(self):
        r = tenacity.retry_all(
            tenacity.retry_if_result(lambda x: x == 1),
            tenacity.retry_if_result(lambda x: isinstance(x, int)))
        self.assertTrue(r(tenacity.Future.construct(1, 1, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 2, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 3, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 1, True)))

    def test_retry_and(self):
        r = (tenacity.retry_if_result(lambda x: x == 1) &
             tenacity.retry_if_result(lambda x: isinstance(x, int)))
        self.assertTrue(r(tenacity.Future.construct(1, 1, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 2, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 3, False)))
        self.assertFalse(r(tenacity.Future.construct(1, 1, True)))

    def test_retry_or(self):
        r = (tenacity.retry_if_result(lambda x: x == "foo") |
             tenacity.retry_if_result(lambda x: isinstance(x, int)))
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
        raise NameError("Hi there, I'm a NameError")


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
        return repr(self.value)


class NoCustomErrorAfterCount(object):
    """Holds counter state for invoking a method several times in a row."""

    def __init__(self, count):
        self.counter = 0
        self.count = count

    def go(self):
        """Raise a CustomError until after count threshold has been crossed.

        Then return True.
        """
        if self.counter < self.count:
            self.counter += 1
            derived_message = "This is a Custom exception class"
            raise CustomError(derived_message)
        return True


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

    def test_defaults(self):
        self.assertTrue(_retryable_default(NoNameErrorAfterCount(5)))
        self.assertTrue(_retryable_default_f(NoNameErrorAfterCount(5)))
        self.assertTrue(_retryable_default(NoCustomErrorAfterCount(5)))
        self.assertTrue(_retryable_default_f(NoCustomErrorAfterCount(5)))


class TestBeforeAfterAttempts(unittest.TestCase):
    _attempt_number = 0

    def test_before_attempts(self):
        TestBeforeAfterAttempts._attempt_number = 0

        def _before(fn, attempt_number):
            TestBeforeAfterAttempts._attempt_number = attempt_number

        @retry(wait=tenacity.wait_fixed(1),
               stop=tenacity.stop_after_attempt(1),
               before=_before)
        def _test_before():
            pass

        _test_before()

        self.assertTrue(TestBeforeAfterAttempts._attempt_number is 1)

    def test_after_attempts(self):
        TestBeforeAfterAttempts._attempt_number = 0

        def _after(fn, attempt_number, trial_time_taken_ms):
            TestBeforeAfterAttempts._attempt_number = attempt_number

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
        TestBeforeAfterAttempts._attempt_number = 0

        def _before_sleep(retry_obj, sleep, last_result):
            self.assertGreater(sleep, 0)
            TestBeforeAfterAttempts._attempt_number = \
                retry_obj.statistics['attempt_number']

        @retry(wait=tenacity.wait_fixed(0.1),
               stop=tenacity.stop_after_attempt(3),
               before_sleep=_before_sleep)
        def _test_before_sleep():
            if TestBeforeAfterAttempts._attempt_number < 2:
                raise Exception("testing before_sleep_attempts handler")
            else:
                pass

        _test_before_sleep()

        self.assertTrue(TestBeforeAfterAttempts._attempt_number is 2)


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
               retry=lambda x: True)
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
               retry=lambda x: True,
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

    def test_retry_error_callback(self):
        num_attempts = 3

        @retry(stop=tenacity.stop_after_attempt(num_attempts),
               retry_error_callback=self._callback)
        def _foobar():
            self._attempt_number += 1
            raise Exception("This exception should not be raised")

        result = _foobar()

        self.assertTrue(self._callback_called)
        self.assertEqual(num_attempts, self._attempt_number)
        self.assertIsInstance(result, tenacity.Future)


if __name__ == '__main__':
    unittest.main()
