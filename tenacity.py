# Copyright 2016 Julien Danjou
# Copyright 2016 Joshua Harlow
# Copyright 2013-2014 Ray Holder
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

import random
import sys
import time

from concurrent import futures
from monotonic import monotonic as now
import six

# sys.maxint / 2, since Python 3.2 doesn't have a sys.maxint...
try:
    MAX_WAIT = sys.maxint / 2
except AttributeError:
    MAX_WAIT = 1073741823


if six.PY2:
    def _capture(fut, tb):
        # TODO(harlowja): delete this in future, since its
        # has to repeatedly calculate this crap.
        fut.set_exception_info(tb[1], tb[2])
else:
    def _capture(fut, tb):
        fut.set_exception(tb[1])


class TryAgain(Exception):
    "Retry the executed function when raised"


def retry(*dargs, **dkw):
    """Decorator function that instantiates the Retrying object.

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


def stop_never(previous_attempt_number, delay_since_first_attempt_ms):
    return False


class stop_after_attempt(object):
    """Strategy that stops when the previous attempt >= max_attempt."""

    def __init__(self, max_attempt_number):
        self.max_attempt_number = max_attempt_number

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        return previous_attempt_number >= self.max_attempt_number


class stop_after_delay(object):
    """Strategy that stops when the time from the first attempt >= limit."""

    def __init__(self, max_delay):
        self.max_delay = max_delay

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        return delay_since_first_attempt_ms >= self.max_delay


class wait_jitter(object):
    """Wait strategy that waits a random amount of time (bounded by a max)."""

    def __init__(self, max):
        self.max = max

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        return random.random() * self.max


class wait_fixed(object):
    """Wait strategy that waits a fixed amount of time between each retry."""

    def __init__(self, wait):
        self.wait_fixed = wait

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        return self.wait_fixed


class wait_none(wait_fixed):
    """Wait strategy that doesn't wait at all before retrying."""

    def __init__(self):
        super(wait_none, self).__init__(0)


class wait_random(object):
    """Wait strategy that waits a random amount of time between min/max."""

    def __init__(self, min=0, max=1000):
        self.wait_random_min = min
        self.wait_random_max = max

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        return random.randint(self.wait_random_min, self.wait_random_max)


class wait_combine(object):
    """Combine several waiting strategies."""

    def __init__(self, *strategies):
        self.wait_funcs = strategies

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        return sum(map(
            lambda x: x(previous_attempt_number, delay_since_first_attempt_ms),
            self.wait_funcs))


class wait_incrementing(object):
    """Wait an incremental amount of time after each attempt.

    Starting at a starting value and incrementing by a value for each attempt
    (and restricting the upper limit to some maximum value).
    """

    def __init__(self, start=0, increment=100, max=MAX_WAIT):
        self.start = start
        self.increment = increment
        self.max = max

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        result = self.start + (
            self.increment * (previous_attempt_number - 1)
        )
        return max(0, min(result, self.max))


class wait_exponential(object):
    """Wait strategy that applies exponential backoff.

    It allows for a customized multiplier and an ability to restrict the
    upper limit to some maximum value.
    """

    def __init__(self, multiplier=1, max=MAX_WAIT, exp_base=2):
        self.multiplier = multiplier
        self.max = max
        self.exp_base = exp_base

    def __call__(self, previous_attempt_number, delay_since_first_attempt_ms):
        exp = self.exp_base ** previous_attempt_number
        result = self.multiplier * exp
        return max(0, min(result, self.max))


def retry_never(attempt):
    """Rejection strategy that never rejects any result."""
    return False


def retry_always(attempt):
    """Rejection strategy that always rejects any result."""
    return True


class retry_if_exception(object):
    """Retry if an exception verifies a predicate."""

    def __init__(self, predicate):
        self.predicate = predicate

    def __call__(self, attempt):
        if attempt.failed:
            return self.predicate(attempt.exception())


class retry_if_exception_type(retry_if_exception):
    """Retry if an exception has been raised of a certain type"""

    def __init__(self, exception_types=Exception):
        self.exception_types = exception_types
        super(retry_if_exception_type, self).__init__(
            lambda e: isinstance(e, exception_types))


class retry_if_result(object):
    """Retry if the result verifies a predicate."""

    def __init__(self, predicate):
        self.predicate = predicate

    def __call__(self, attempt):
        if not attempt.failed:
            return self.predicate(attempt.result())


class retry_any(object):
    """Retry if any of the retries condition is valid."""

    def __init__(self, *retries):
        self.retries = retries

    def __call__(self, attempt):
        return any(map(lambda x: x(attempt), self.retries))


class Retrying(object):
    """Retrying controller."""

    def __init__(self,
                 stop=stop_never, wait=wait_none(),
                 sleep=time.sleep,
                 retry=retry_if_exception_type(),
                 before_attempts=None,
                 after_attempts=None):
        self.sleep = sleep
        self.stop = stop
        self.wait = wait
        self.retry = retry
        self._before_attempts = before_attempts
        self._after_attempts = after_attempts

    def call(self, fn, *args, **kwargs):
        start_time = int(round(now() * 1000))
        attempt_number = 1
        while True:
            if self._before_attempts:
                self._before_attempts(attempt_number)

            fut = Future(attempt_number)
            try:
                fut.set_result(fn(*args, **kwargs))
            except TryAgain:
                retry = True
            except Exception:
                tb = sys.exc_info()
                try:
                    _capture(fut, tb)
                finally:
                    del tb
                retry = self.retry(fut)
            else:
                retry = self.retry(fut)

            if not retry:
                return fut.result()

            if self._after_attempts:
                self._after_attempts(attempt_number)

            delay_since_first_attempt_ms = int(
                round(now() * 1000)
            ) - start_time
            if self.stop(attempt_number, delay_since_first_attempt_ms):
                six.raise_from(RetryError(fut), fut.exception())

            if self.wait:
                sleep = self.wait(attempt_number, delay_since_first_attempt_ms)
            else:
                sleep = 0
            self.sleep(sleep / 1000.0)

            attempt_number += 1


class Future(futures.Future):
    """Encapsulates a (future or past) attempted call to a target function."""

    def __init__(self, attempt_number):
        super(Future, self).__init__()
        self.attempt_number = attempt_number

    @property
    def failed(self):
        """Return whether a exception is being held in this future."""
        return self.exception() is not None

    @classmethod
    def construct(cls, attempt_number, value, has_exception):
        """Helper (for testing) for making these objects easily."""
        fut = cls(attempt_number)
        if has_exception:
            fut.set_exception(value)
        else:
            fut.set_result(value)
        return fut


class RetryError(Exception):
    "Encapsulates the last attempt instance right before giving up"

    def __init__(self, last_attempt):
        self.last_attempt = last_attempt

    def __str__(self):
        return "RetryError[{0}]".format(self.last_attempt)
