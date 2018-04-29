# -*- coding: utf-8 -*-
# Copyright 2016-2018 Julien Danjou
# Copyright 2017 Elisey Zanko
# Copyright 2016 Étienne Bersac
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

try:
    import asyncio
except ImportError:
    asyncio = None

try:
    import tornado
except ImportError:
    tornado = None

import sys
import threading
from concurrent import futures

import six

from tenacity import _utils
from tenacity import wait as _wait

# Import all built-in retry strategies for easier usage.
from .retry import retry_all  # noqa
from .retry import retry_always  # noqa
from .retry import retry_any  # noqa
from .retry import retry_if_exception  # noqa
from .retry import retry_if_exception_type  # noqa
from .retry import retry_if_not_result  # noqa
from .retry import retry_if_result  # noqa
from .retry import retry_never  # noqa
from .retry import retry_unless_exception_type  # noqa

# Import all nap strategies for easier usage.
from .nap import sleep  # noqa
from .nap import sleep_using_event  # noqa

# Import all built-in stop strategies for easier usage.
from .stop import stop_after_attempt  # noqa
from .stop import stop_after_delay  # noqa
from .stop import stop_all  # noqa
from .stop import stop_any  # noqa
from .stop import stop_never  # noqa
from .stop import stop_when_event_set  # noqa

# Import all built-in wait strategies for easier usage.
from .wait import wait_chain  # noqa
from .wait import wait_combine  # noqa
from .wait import wait_exponential  # noqa
from .wait import wait_fixed  # noqa
from .wait import wait_incrementing  # noqa
from .wait import wait_none  # noqa
from .wait import wait_random  # noqa
from .wait import wait_random_exponential  # noqa
from .wait import wait_random_exponential as wait_full_jitter  # noqa

# Import all built-in before strategies for easier usage.
from .before import before_log  # noqa
from .before import before_nothing  # noqa

# Import all built-in after strategies for easier usage.
from .after import after_log  # noqa
from .after import after_nothing  # noqa

# Import all built-in after strategies for easier usage.
from .before_sleep import before_sleep_log  # noqa
from .before_sleep import before_sleep_nothing  # noqa


def retry(*dargs, **dkw):
    """Wrap a function with a new `Retrying` object.

    :param dargs: positional arguments passed to Retrying object
    :param dkw: keyword arguments passed to the Retrying object
    """
    # support both @retry and @retry() as valid syntax
    if len(dargs) == 1 and callable(dargs[0]):
        return retry()(dargs[0])
    else:
        def wrap(f):
            if asyncio and asyncio.iscoroutinefunction(f):
                r = AsyncRetrying(*dargs, **dkw)
            elif tornado and hasattr(tornado.gen, 'is_coroutine_function') \
                    and tornado.gen.is_coroutine_function(f):
                r = TornadoRetrying(*dargs, **dkw)
            else:
                r = Retrying(*dargs, **dkw)

            return r.wraps(f)

        return wrap


class TryAgain(Exception):
    """Always retry the executed function when raised."""


NO_RESULT = object()


class DoAttempt(object):
    pass


class DoSleep(float):
    pass


_unset = object()


class RetryError(Exception):
    """Encapsulates the last attempt instance right before giving up."""

    def __init__(self, last_attempt):
        self.last_attempt = last_attempt

    def reraise(self):
        if self.last_attempt.failed:
            raise self.last_attempt.result()
        raise self

    def __str__(self):
        return "{0}[{1}]".format(self.__class__.__name__, self.last_attempt)


class BaseRetrying(object):

    def __init__(self,
                 sleep=sleep,
                 stop=stop_never, wait=wait_none(),
                 retry=retry_if_exception_type(),
                 before=before_nothing,
                 after=after_nothing,
                 before_sleep=before_sleep_nothing,
                 reraise=False,
                 retry_error_cls=RetryError,
                 retry_error_callback=None):
        self.sleep = sleep
        self.stop = stop
        self.wait = wait
        self.retry = retry
        self.before = before
        self.after = after
        self.before_sleep = before_sleep
        self.reraise = reraise
        self._local = threading.local()
        # This will allow for passing in the result and handling
        # the older versions of these functions that do not take
        # the prior result.
        self._wait_takes_result = self._waiter_takes_last_result(wait)
        self.retry_error_cls = retry_error_cls
        self.retry_error_callback = retry_error_callback

    def copy(self, sleep=_unset, stop=_unset, wait=_unset,
             retry=_unset, before=_unset, after=_unset, before_sleep=_unset,
             reraise=_unset):
        """Copy this object with some parameters changed if needed."""
        if before_sleep is _unset:
            before_sleep = self.before_sleep
        return self.__class__(
            sleep=self.sleep if sleep is _unset else sleep,
            stop=self.stop if stop is _unset else stop,
            wait=self.wait if wait is _unset else wait,
            retry=self.retry if retry is _unset else retry,
            before=self.before if before is _unset else before,
            after=self.after if after is _unset else after,
            before_sleep=before_sleep,
            reraise=self.reraise if after is _unset else reraise,
        )

    @staticmethod
    def _waiter_takes_last_result(waiter):
        if not six.callable(waiter):
            return False
        if isinstance(waiter, _wait.wait_base):
            waiter = waiter.__call__
        waiter_spec = _utils.getargspec(waiter)
        return 'last_result' in waiter_spec.args

    def __repr__(self):
        attrs = dict(
            _utils.visible_attrs(self, attrs={'me': id(self)}),
            __class__=self.__class__.__name__,
        )
        return ("<%(__class__)s object at 0x%(me)x (stop=%(stop)s, "
                "wait=%(wait)s, sleep=%(sleep)s, retry=%(retry)s, "
                "before=%(before)s, after=%(after)s)>") % (attrs)

    @property
    def statistics(self):
        """Return a dictionary of runtime statistics.

        This dictionary will be empty when the controller has never been
        ran. When it is running or has ran previously it should have (but
        may not) have useful and/or informational keys and values when
        running is underway and/or completed.

        .. warning:: The keys in this dictionary **should** be some what
                     stable (not changing), but there existence **may**
                     change between major releases as new statistics are
                     gathered or removed so before accessing keys ensure that
                     they actually exist and handle when they do not.

        .. note:: The values in this dictionary are local to the thread
                  running call (so if multiple threads share the same retrying
                  object - either directly or indirectly) they will each have
                  there own view of statistics they have collected (in the
                  future we may provide a way to aggregate the various
                  statistics from each thread).
        """
        try:
            return self._local.statistics
        except AttributeError:
            self._local.statistics = {}
            return self._local.statistics

    def wraps(self, f):
        """Wrap a function for retrying.

        :param f: A function to wraps for retrying.
        """
        @six.wraps(f)
        def wrapped_f(*args, **kw):
            return self.call(f, *args, **kw)

        def retry_with(*args, **kwargs):
            return self.copy(*args, **kwargs).wraps(f)

        wrapped_f.retry = self
        wrapped_f.retry_with = retry_with

        return wrapped_f

    def begin(self, fn):
        self.fn = fn
        self.statistics.clear()
        self.statistics['start_time'] = _utils.now()
        self.statistics['attempt_number'] = 1
        self.statistics['idle_for'] = 0

    def iter(self, result, exc_info, start_time):  # noqa
        fut = Future(self.statistics['attempt_number'])
        if result is not NO_RESULT:
            trial_end_time = _utils.now()
            fut.set_result(result)
            retry = self.retry(fut)
        elif exc_info:
            trial_end_time = _utils.now()
            t, e, tb = exc_info
            _utils.capture(fut, exc_info)
            if isinstance(e, TryAgain):
                retry = True
            else:
                retry = self.retry(fut)
        else:
            if self.before is not None:
                self.before(self.fn, self.statistics['attempt_number'])

            return DoAttempt()

        if not retry:
            return fut.result()

        if self.after is not None:
            trial_time_taken = trial_end_time - start_time
            self.after(self.fn, self.statistics['attempt_number'],
                       trial_time_taken)

        delay_since_first_attempt = (
            _utils.now() - self.statistics['start_time']
        )
        self.statistics['delay_since_first_attempt'] = \
            delay_since_first_attempt
        if self.stop(self.statistics['attempt_number'],
                     delay_since_first_attempt):
            if self.retry_error_callback:
                return self.retry_error_callback(fut)
            retry_exc = self.retry_error_cls(fut)
            if self.reraise:
                raise retry_exc.reraise()
            six.raise_from(retry_exc, fut.exception())

        if self.wait:
            if self._wait_takes_result:
                sleep = self.wait(self.statistics['attempt_number'],
                                  delay_since_first_attempt, last_result=fut)
            else:
                sleep = self.wait(self.statistics['attempt_number'],
                                  delay_since_first_attempt)
        else:
            sleep = 0
        self.statistics['idle_for'] += sleep
        self.statistics['attempt_number'] += 1

        if self.before_sleep is not None:
            self.before_sleep(self, sleep=sleep, last_result=fut)

        return DoSleep(sleep)


class Retrying(BaseRetrying):
    """Retrying controller."""

    def call(self, fn, *args, **kwargs):
        self.begin(fn)

        result = NO_RESULT
        exc_info = None
        start_time = _utils.now()

        while True:
            do = self.iter(result=result, exc_info=exc_info,
                           start_time=start_time)
            if isinstance(do, DoAttempt):
                try:
                    result = fn(*args, **kwargs)
                    continue
                except BaseException:
                    exc_info = sys.exc_info()
                    continue
            elif isinstance(do, DoSleep):
                result = NO_RESULT
                exc_info = None
                self.sleep(do)
            else:
                return do

    __call__ = call


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
        """Construct a new Future object."""
        fut = cls(attempt_number)
        if has_exception:
            fut.set_exception(value)
        else:
            fut.set_result(value)
        return fut


if asyncio:
    from tenacity._asyncio import AsyncRetrying

if tornado:
    from tenacity.tornadoweb import TornadoRetrying
