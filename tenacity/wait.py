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

import abc
import random
from fractions import Fraction

import six

from tenacity import _utils


_unset = object()


def _make_wait_retry_state(previous_attempt_number, delay_since_first_attempt,
                           last_result=None):
    required_parameter_unset = (previous_attempt_number is _unset or
                                delay_since_first_attempt is _unset)
    if required_parameter_unset:
        missing = []
        if previous_attempt_number is _unset:
            missing.append('previous_attempt_number')
        if delay_since_first_attempt is _unset:
            missing.append('delay_since_first_attempt')
        missing_str = ', '.join(repr(s) for s in missing)
        raise TypeError('wait func missing parameters: ' + missing_str)

    from tenacity import RetryCallState
    retry_state = RetryCallState(None, None, (), {})
    retry_state.attempt_number = previous_attempt_number
    if last_result is not None:
        retry_state.outcome = last_result
    else:
        retry_state.set_result(None)
    # Ensure outcome_timestamp - start_time is *exactly* equal to the delay to
    # avoid complexity in test code.
    retry_state.start_time = Fraction(retry_state.start_time)
    retry_state.outcome_timestamp = (
        retry_state.start_time + Fraction(delay_since_first_attempt))
    assert retry_state.seconds_since_start == delay_since_first_attempt
    return retry_state


def _wait_dunder_call_accept_old_params(fn):
    @six.wraps(fn)
    def new_fn(self,
               previous_attempt_number=_unset,
               delay_since_first_attempt=_unset,
               last_result=None,
               retry_state=None):
        if retry_state is None:
            retry_state = _make_wait_retry_state(
                previous_attempt_number=previous_attempt_number,
                delay_since_first_attempt=delay_since_first_attempt,
                last_result=last_result)
        return fn(self, retry_state=retry_state)
    return new_fn


@six.add_metaclass(abc.ABCMeta)
class wait_base(object):
    """Abstract base class for wait strategies."""

    @abc.abstractmethod
    def __call__(self, retry_state):
        pass

    def __add__(self, other):
        return wait_combine(self, other)

    def __radd__(self, other):
        # make it possible to use multiple waits with the built-in sum function
        if other == 0:
            return self
        return self.__add__(other)


class wait_fixed(wait_base):
    """Wait strategy that waits a fixed amount of time between each retry."""

    def __init__(self, wait):
        self.wait_fixed = wait

    @_wait_dunder_call_accept_old_params
    def __call__(self, retry_state):
        return self.wait_fixed


class wait_none(wait_fixed):
    """Wait strategy that doesn't wait at all before retrying."""

    def __init__(self):
        super(wait_none, self).__init__(0)


class wait_random(wait_base):
    """Wait strategy that waits a random amount of time between min/max."""

    def __init__(self, min=0, max=1):  # noqa
        self.wait_random_min = min
        self.wait_random_max = max

    @_wait_dunder_call_accept_old_params
    def __call__(self, retry_state):
        return (self.wait_random_min +
                (random.random() *
                 (self.wait_random_max - self.wait_random_min)))


class wait_combine(wait_base):
    """Combine several waiting strategies."""

    def __init__(self, *strategies):
        self.wait_funcs = tuple(_wait_func_accept_retry_state(strategy)
                                for strategy in strategies)

    @_wait_dunder_call_accept_old_params
    def __call__(self, retry_state):
        return sum(x(retry_state=retry_state) for x in self.wait_funcs)


class wait_chain(wait_base):
    """Chain two or more waiting strategies.

    If all strategies are exhausted, the very last strategy is used
    thereafter.

    For example::

        @retry(wait=wait_chain(*[wait_fixed(1) for i in range(3)] +
                               [wait_fixed(2) for j in range(5)] +
                               [wait_fixed(5) for k in range(4)))
        def wait_chained():
            print("Wait 1s for 3 attempts, 2s for 5 attempts and 5s
                   thereafter.")
    """

    def __init__(self, *strategies):
        self.strategies = [_wait_func_accept_retry_state(strategy)
                           for strategy in strategies]

    @_wait_dunder_call_accept_old_params
    def __call__(self, retry_state):
        wait_func_no = min(max(retry_state.attempt_number, 1),
                           len(self.strategies))
        wait_func = self.strategies[wait_func_no - 1]
        return wait_func(retry_state=retry_state)


class wait_incrementing(wait_base):
    """Wait an incremental amount of time after each attempt.

    Starting at a starting value and incrementing by a value for each attempt
    (and restricting the upper limit to some maximum value).
    """

    def __init__(self, start=0, increment=100, max=_utils.MAX_WAIT):  # noqa
        self.start = start
        self.increment = increment
        self.max = max

    @_wait_dunder_call_accept_old_params
    def __call__(self, retry_state):
        result = self.start + (
            self.increment * (retry_state.attempt_number - 1)
        )
        return max(0, min(result, self.max))


class wait_exponential(wait_base):
    """Wait strategy that applies exponential backoff.

    It allows for a customized multiplier and an ability to restrict the
    upper limit to some maximum value.

    The intervals are fixed (i.e. there is no jitter), so this strategy is
    suitable for balancing retries against latency when a required resource is
    unavailable for an unknown duration, but *not* suitable for resolving
    contention between multiple processes for a shared resource. Use
    wait_random_exponential for the latter case.
    """

    def __init__(self, multiplier=1, max=_utils.MAX_WAIT, exp_base=2):  # noqa
        self.multiplier = multiplier
        self.max = max
        self.exp_base = exp_base

    @_wait_dunder_call_accept_old_params
    def __call__(self, retry_state):
        try:
            exp = self.exp_base ** retry_state.attempt_number
            result = self.multiplier * exp
        except OverflowError:
            return self.max
        return max(0, min(result, self.max))


class wait_random_exponential(wait_exponential):
    """Random wait with exponentially widening window.

    An exponential backoff strategy used to mediate contention between multiple
    unco-ordinated processes for a shared resource in distributed systems. This
    is the sense in which "exponential backoff" is meant in e.g. Ethernet
    networking, and corresponds to the "Full Jitter" algorithm described in
    this blog post:

    https://www.awsarchitectureblog.com/2015/03/backoff.html

    Each retry occurs at a random time in a geometrically expanding interval.
    It allows for a custom multiplier and an ability to restrict the upper
    limit of the random interval to some maximum value.

    Example::

        wait_random_exponential(multiplier=0.5,  # initial window 0.5s
                                max=60)          # max 60s timeout

    When waiting for an unavailable resource to become available again, as
    opposed to trying to resolve contention for a shared resource, the
    wait_exponential strategy (which uses a fixed interval) may be preferable.
    """

    @_wait_dunder_call_accept_old_params
    def __call__(self, retry_state):
        high = super(wait_random_exponential, self).__call__(
            retry_state=retry_state)
        return random.uniform(0, high)


def _func_takes_last_result(waiter):
    if not six.callable(waiter):
        return False
    if isinstance(waiter, wait_base):
        waiter = waiter.__call__
    waiter_spec = _utils.getargspec(waiter)
    return 'last_result' in waiter_spec.args


def _wait_func_accept_retry_state(wait_func):
    if not six.callable(wait_func):
        return wait_func

    takes_retry_state = _utils._func_takes_retry_state(wait_func)
    if takes_retry_state:
        return wait_func

    takes_last_result = _func_takes_last_result(wait_func)
    if takes_last_result:
        @six.wraps(wait_func)
        def wrapped_wait_func(retry_state):
            return wait_func(
                retry_state.attempt_number,
                retry_state.seconds_since_start,
                last_result=retry_state.outcome,
            )
    else:
        @six.wraps(wait_func)
        def wrapped_wait_func(retry_state):
            return wait_func(
                retry_state.attempt_number,
                retry_state.seconds_since_start,
            )
    return wrapped_wait_func
