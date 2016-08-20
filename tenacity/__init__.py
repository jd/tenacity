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

from concurrent import futures
import sys
import time

from monotonic import monotonic as now
import six

# Import all built-in retry strategies for easier usage.
from .retry import retry_always  # noqa
from .retry import retry_any  # noqa
from .retry import retry_if_exception  # noqa
from .retry import retry_if_exception_type  # noqa
from .retry import retry_if_result  # noqa
from .retry import retry_never  # noqa

# Import all built-in stop strategies for easier usage.
from .stop import stop_after_attempt  # noqa
from .stop import stop_after_delay  # noqa
from .stop import stop_never  # noqa

# Import all built-in wait strategies for easier usage.
from .wait import wait_combine  # noqa
from .wait import wait_exponential  # noqa
from .wait import wait_fixed  # noqa
from .wait import wait_incrementing  # noqa
from .wait import wait_jitter  # noqa
from .wait import wait_none  # noqa
from .wait import wait_random  # noqa

from tenacity import _utils


def retry(*dargs, **dkw):
    """Decorator function that wraps + instantiates a ``Retrying`` object.

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


class TryAgain(Exception):
    """Always retry the executed function when raised."""


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
                    _utils.capture(fut, tb)
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
