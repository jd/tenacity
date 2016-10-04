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
import threading
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
from .wait import wait_chain  # noqa
from .wait import wait_combine  # noqa
from .wait import wait_exponential  # noqa
from .wait import wait_fixed  # noqa
from .wait import wait_incrementing  # noqa
from .wait import wait_jitter  # noqa
from .wait import wait_none  # noqa
from .wait import wait_random  # noqa

# Import all built-in before strategies for easier usage.
from .before import before_log  # noqa
from .before import before_nothing  # noqa

# Import all built-in after strategies for easier usage.
from .after import after_log  # noqa
from .after import after_nothing  # noqa

from tenacity import _utils


def retry(*dargs, **dkw):
    """Decorator function that wraps + instantiates a ``Retrying`` object.

    @param *dargs: positional arguments passed to Retrying object
    @param **dkw: keyword arguments passed to the Retrying object
    """
    # support both @retry and @retry() as valid syntax
    if len(dargs) == 1 and callable(dargs[0]):
        r = Retrying()

        def wrap_simple(f):

            @six.wraps(f)
            def wrapped_f(*args, **kw):
                return r.call(f, *args, **kw)

            wrapped_f.retry = r
            return wrapped_f

        return wrap_simple(dargs[0])

    else:
        r = Retrying(*dargs, **dkw)

        def wrap(f):

            @six.wraps(f)
            def wrapped_f(*args, **kw):
                return r.call(f, *args, **kw)

            wrapped_f.retry = r
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
                 before=before_nothing,
                 after=after_nothing,
                 reraise=False):
        self.sleep = sleep
        self.stop = stop
        self.wait = wait
        self.retry = retry
        self.before = before
        self.after = after
        self.reraise = reraise
        self._local = threading.local()

    def __repr__(self):
        attrs = _utils.visible_attrs(self, attrs={'me': id(self)})
        return ("<Retrying object at 0x%(me)x (stop=%(stop)s, "
                "wait=%(wait)s, sleep=%(sleep)s, retry=%(retry)s, "
                "before=%(before)s, after=%(after)s)>") % (attrs)

    @property
    def statistics(self):
        """A dictionary of runtime statistics this controller has gathered.

        This dictionary will be empty when the controller has never been
        ran. When it is running or has ran previously it should have (but
        may not) have useful and/or informational keys and values when
        running is underway and/or completed.

        .. warning:: The keys in this dictionary **should** be some what
                     stable (not changing), but there existence **may**
                     change between major releases as new statistics are
                     gathered or removed so before accessing keys ensure that
                     they actually exist and handle when they do not.
        """
        try:
            return self._local.statistics
        except AttributeError:
            self._local.statistics = {}
            return self._local.statistics

    def call(self, fn, *args, **kwargs):
        self.statistics.clear()
        start_time = now()
        self.statistics['start_time'] = start_time
        attempt_number = 1
        self.statistics['attempt_number'] = attempt_number
        self.statistics['idle_for'] = 0
        while True:
            trial_start_time = now()
            if self.before is not None:
                self.before(fn, attempt_number)

            fut = Future(attempt_number)
            try:
                result = fn(*args, **kwargs)
            except TryAgain:
                trial_end_time = now()
                retry = True
            except Exception:
                trial_end_time = now()
                tb = sys.exc_info()
                try:
                    _utils.capture(fut, tb)
                finally:
                    del tb
                retry = self.retry(fut)
            else:
                trial_end_time = now()
                fut.set_result(result)
                retry = self.retry(fut)

            if not retry:
                return fut.result()

            if self.after is not None:
                trial_time_taken = trial_end_time - trial_start_time
                self.after(fn, attempt_number, trial_time_taken)

            delay_since_first_attempt = now() - start_time
            self.statistics['delay_since_first_attempt'] = \
                delay_since_first_attempt
            if self.stop(attempt_number, delay_since_first_attempt):
                if self.reraise:
                    raise RetryError(fut).reraise()
                six.raise_from(RetryError(fut), fut.exception())

            if self.wait:
                sleep = self.wait(attempt_number, delay_since_first_attempt)
            else:
                sleep = 0
            self.statistics['idle_for'] += sleep
            self.sleep(sleep)

            attempt_number += 1
            self.statistics['attempt_number'] = attempt_number


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

    def reraise(self):
        if self.last_attempt.failed:
            raise self.last_attempt.result()
        raise self

    def __str__(self):
        return "RetryError[{0}]".format(self.last_attempt)
