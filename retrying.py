## Copyright 2013-2014 Ray Holder
##
## Licensed under the Apache License, Version 2.0 (the "License");
## you may not use this file except in compliance with the License.
## You may obtain a copy of the License at
##
## http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing, software
## distributed under the License is distributed on an "AS IS" BASIS,
## WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
## See the License for the specific language governing permissions and
## limitations under the License.

import random
import six
import sys
import time
import traceback


# sys.maxint / 2, since Python 3.2 doesn't have a sys.maxint...
try:
    MAX_WAIT = sys.maxint / 2
except AttributeError:
    MAX_WAIT = 1073741823


def _val_or(val, default):
    if val is None:
        return default
    return val


def _retry_if_exception_of_type(retryable_types):
    def _retry_if_exception_these_types(exception):
        return isinstance(exception, retryable_types)
    return _retry_if_exception_these_types


def retry(*dargs, **dkw):
    """
    Decorator function that instantiates the Retrying object
    @param *dargs: positional arguments passed to Retrying object
    @param **dkw: keyword arguments passed to the Retrying object
    """
    # support both @retry and @retry() as valid syntax
    if len(dargs) == 1 and callable(dargs[0]):
        def wrap_simple(f):

            @six.wraps(f)
            def wrapped_f(*args, **kw):
                return Retrying().call(f, *args, **kw)

            return wrapped_f

        return wrap_simple(dargs[0])

    else:
        def wrap(f):

            @six.wraps(f)
            def wrapped_f(*args, **kw):
                return Retrying(*dargs, **dkw).call(f, *args, **kw)

            return wrapped_f

        return wrap


class _stop_after_attempt(object):
    """Strategy that stops when the previous attempt >= max_attempt."""

    def __init__(self, stop_max_attempt_number):
        self.stop_max_attempt_number = stop_max_attempt_number

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        return previous_attempt_number >= self.stop_max_attempt_number


class _stop_after_delay(object):
    """Strategy that stops when the time from the first attempt >= limit."""

    def __init__(self, stop_max_delay):
        self.stop_max_delay = stop_max_delay

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        return delay_since_first_attempt_ms >= self.stop_max_delay


class _fixed_sleep(object):
    """Wait strategy that waits a fixed amount of time between each retry."""

    def __init__(self, wait_fixed):
        self.wait_fixed = wait_fixed

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        return self.wait_fixed


class _no_sleep(_fixed_sleep):
    """Wait strategy that doesn't wait at all before retrying."""

    def __init__(self):
        super(_no_sleep, self).__init__(0)


class _random_sleep(object):
    """Wait strategy that waits a random amount of time between min/max."""

    def __init__(self, wait_random_min, wait_random_max):
        self.wait_random_min = wait_random_min
        self.wait_random_max = wait_random_max

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        return random.randint(self.wait_random_min, self.wait_random_max)


class _incrementing_sleep(object):
    """
    Wait strategy that waits an incremental amount of time after each
    attempt, starting at a starting value and incrementing by a value for
    each attempt (and restricting the upper limit to some maximum value).
    """

    def __init__(self, wait_incrementing_start, wait_incrementing_increment,
                 wait_incrementing_max):
        self.wait_incrementing_start = wait_incrementing_start
        self.wait_incrementing_increment = wait_incrementing_increment
        self.wait_incrementing_max = wait_incrementing_max

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        result = self.wait_incrementing_start + (self.wait_incrementing_increment * (previous_attempt_number - 1))
        if result > self.wait_incrementing_max:
            result = self.wait_incrementing_max
        if result < 0:
            result = 0
        return result


class _exponential_sleep(object):
    """Wait strategy that applies exponential backoff.

    It allows for a customized multiplier and an ability to restrict the
    upper limit to some maximum value.
    """

    #: Defaults to 2^n (where n is the prior attempt number/count).
    EXP_BASE = 2

    def __init__(self, wait_exponential_multiplier, wait_exponential_max):
        self.wait_exponential_multiplier = wait_exponential_multiplier
        self.wait_exponential_max = wait_exponential_max

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        exp = self.EXP_BASE ** previous_attempt_number
        result = self.wait_exponential_multiplier * exp
        if result > self.wait_exponential_max:
            result = self.wait_exponential_max
        if result < 0:
            result = 0
        return result


def _never_reject(result):
    """Rejection strategy that never rejects any result."""
    return False


def _always_reject(result):
    """Rejection strategy that always rejects any result."""
    return True


class _MaybeReject(object):
    """Rejection strategy that proxies to 2 functions to reject (or not)."""

    def __init__(self, retry_on_exception=None,
                 retry_on_result=None):
        self.retry_on_exception = retry_on_exception
        self.retry_on_result = retry_on_result

    def __call__(self, attempt):
        reject = False
        if attempt.has_exception:
            if self.retry_on_exception is not None:
                reject |= self.retry_on_exception(attempt.value[1])
        else:
            if self.retry_on_result is not None:
                reject |= self.retry_on_result(attempt.value)
        return reject


def _select_stop_strategy(stop=None, stop_max_attempt_number=None,
                          stop_max_delay=None, stop_func=None):
    if stop_func is not None:
        return stop_func

    if stop is not None:
        for s_name, s in [
                ('stop_after_attempt',
                 _stop_after_attempt(_val_or(stop_max_attempt_number, 5))),
                ('stop_after_delay',
                 _stop_after_delay(_val_or(stop_max_delay, 100))),
            ]:
            if s_name == stop:
                return s
        # Match the original behavior if we didn't match to any
        # known strategy
        raise AttributeError("No stop strategy with name '%s'" % stop)

    stop_strategies = []

    if stop_max_attempt_number is not None:
        stop_strategies.append(_stop_after_attempt(stop_max_attempt_number))

    if stop_max_delay is not None:
        stop_strategies.append(_stop_after_delay(stop_max_delay))

    def any_strategy(previous_attempt_number, delay_since_first_attempt_ms):
        return any(s(previous_attempt_number, delay_since_first_attempt_ms)
                   for s in stop_strategies)

    return any_strategy


def _select_reject_strategy(retry_on_exception=None, retry_on_result=None):
    if retry_on_exception is None:
        retry_on_exception = _always_reject
    else:
        if isinstance(retry_on_exception, (tuple)):
            retry_on_exception = _retry_if_exception_of_type(
                retry_on_exception)
    if retry_on_result is None:
        retry_on_result = _never_reject
    return _MaybeReject(retry_on_result=retry_on_result,
                        retry_on_exception=retry_on_exception)


def _select_wait_strategy(wait_func=None, wait=None,
                          wait_fixed=None,
                          wait_random_min=None, wait_random_max=None,
                          wait_incrementing_start=None,
                          wait_incrementing_increment=None,
                          wait_incrementing_max=None,
                          wait_exponential_multiplier=None,
                          wait_exponential_max=None):
    if wait_func is not None:
        return wait_func

    if wait is not None:
        for w_name, w in [
                ('exponential_sleep',
                 _exponential_sleep(_val_or(wait_exponential_multiplier, 1),
                                    _val_or(wait_exponential_max, MAX_WAIT))),
                ('incrementing_sleep',
                 _incrementing_sleep(_val_or(wait_incrementing_start, 0),
                                     _val_or(wait_incrementing_increment, 100),
                                     _val_or(wait_incrementing_max, MAX_WAIT))),
                ('fixed_sleep',
                 _fixed_sleep(_val_or(wait_fixed, 1000))),
                ('no_sleep', _no_sleep()),
                ('random_sleep',
                 _random_sleep(_val_or(wait_random_min, 0),
                               _val_or(wait_random_max, 1000))),
            ]:
            if w_name == wait:
                return w
        # Match the original behavior if we didn't match to any
        # known strategy
        raise AttributeError("No wait strategy with name '%s'" % wait)

    wait_strategies = []

    if wait_fixed is not None:
        wait_strategies.append(_fixed_sleep(wait_fixed))

    if wait_random_min is not None or wait_random_max is not None:
        wait_random_min = _val_or(wait_random_min, 0)
        wait_random_max = _val_or(wait_random_max, 1000)
        wait_strategies.append(_random_sleep(wait_random_min,
                                             wait_random_max))

    if (wait_incrementing_start is not None or
           wait_incrementing_increment is not None):
        wait_incrementing_start = _val_or(wait_incrementing_start, 0)
        wait_incrementing_increment = _val_or(wait_incrementing_increment, 100)
        wait_incrementing_max = _val_or(wait_incrementing_max, MAX_WAIT)
        wait_strategies.append(
            _incrementing_sleep(wait_incrementing_start,
                                wait_incrementing_increment,
                                wait_incrementing_max))

    if (wait_exponential_multiplier is not None or
           wait_exponential_max is not None):
        wait_exponential_multiplier = _val_or(wait_exponential_multiplier, 1)
        wait_exponential_max = _val_or(wait_exponential_max, MAX_WAIT)
        wait_strategies.append(
            _exponential_sleep(wait_exponential_multiplier,
                               wait_exponential_max))

    if not wait_strategies:
        wait_strategies.append(_no_sleep())

    def max_strategy(previous_attempt_number, delay_since_first_attempt_ms):
        return max(s(previous_attempt_number, delay_since_first_attempt_ms)
                   for s in wait_strategies)

    return max_strategy


class Retrying(object):
    """Retrying controller."""

    def __init__(self,
                 stop=None, wait=None,
                 stop_max_attempt_number=None,
                 stop_max_delay=None,
                 wait_fixed=None,
                 wait_random_min=None, wait_random_max=None,
                 wait_incrementing_start=None, wait_incrementing_increment=None,
                 wait_incrementing_max=None,
                 wait_exponential_multiplier=None, wait_exponential_max=None,
                 retry_on_exception=None,
                 retry_on_result=None,
                 wrap_exception=False,
                 stop_func=None,
                 wait_func=None,
                 wait_jitter_max=None,
                 before_attempts=None,
                 after_attempts=None):
        self.stop = _select_stop_strategy(
            stop=stop, stop_func=stop_func,
            stop_max_attempt_number=stop_max_attempt_number,
            stop_max_delay=stop_max_delay)
        self.wait = _select_wait_strategy(
            wait_func=wait_func, wait=wait,
            wait_fixed=wait_fixed,
            wait_random_min=wait_random_min, wait_random_max=wait_random_max,
            wait_incrementing_start=wait_incrementing_start,
            wait_incrementing_increment=wait_incrementing_increment,
            wait_incrementing_max=wait_incrementing_max,
            wait_exponential_multiplier=wait_exponential_multiplier,
            wait_exponential_max=wait_exponential_max)
        self.should_reject = _select_reject_strategy(
            retry_on_exception=retry_on_exception,
            retry_on_result=retry_on_result)
        self._wrap_exception = wrap_exception
        self._before_attempts = before_attempts
        self._after_attempts = after_attempts
        self._wait_jitter_max = wait_jitter_max

    def call(self, fn, *args, **kwargs):
        start_time = int(round(time.time() * 1000))
        attempt_number = 1
        while True:
            if self._before_attempts:
                self._before_attempts(attempt_number)

            try:
                attempt = Attempt(fn(*args, **kwargs), attempt_number, False)
            except:
                tb = sys.exc_info()
                attempt = Attempt(tb, attempt_number, True)

            if not self.should_reject(attempt):
                return attempt.get(self._wrap_exception)

            if self._after_attempts:
                self._after_attempts(attempt_number)

            delay_since_first_attempt_ms = int(round(time.time() * 1000)) - start_time
            if self.stop(attempt_number, delay_since_first_attempt_ms):
                if not self._wrap_exception and attempt.has_exception:
                    # get() on an attempt with an exception should cause it to be raised, but raise just in case
                    raise attempt.get()
                else:
                    raise RetryError(attempt)
            else:
                sleep = self.wait(attempt_number, delay_since_first_attempt_ms)
                if self._wait_jitter_max:
                    jitter = random.random() * self._wait_jitter_max
                    sleep = sleep + max(0, jitter)
                time.sleep(sleep / 1000.0)

            attempt_number += 1


class Attempt(object):
    """
    An Attempt encapsulates a call to a target function that may end as a
    normal return value from the function or an Exception depending on what
    occurred during the execution.
    """

    def __init__(self, value, attempt_number, has_exception):
        self.value = value
        self.attempt_number = attempt_number
        self.has_exception = has_exception

    def get(self, wrap_exception=False):
        """
        Return the return value of this Attempt instance or raise an Exception.
        If wrap_exception is true, this Attempt is wrapped inside of a
        RetryError before being raised.
        """
        if self.has_exception:
            if wrap_exception:
                raise RetryError(self)
            else:
                six.reraise(self.value[0], self.value[1], self.value[2])
        else:
            return self.value

    def __repr__(self):
        if self.has_exception:
            return "Attempts: {0}, Error:\n{1}".format(self.attempt_number, "".join(traceback.format_tb(self.value[2])))
        else:
            return "Attempts: {0}, Value: {1}".format(self.attempt_number, self.value)


class RetryError(Exception):
    """
    A RetryError encapsulates the last Attempt instance right before giving up.
    """

    def __init__(self, last_attempt):
        self.last_attempt = last_attempt

    def __str__(self):
        return "RetryError[{0}]".format(self.last_attempt)
