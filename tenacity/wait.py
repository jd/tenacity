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

import six

from tenacity import _utils


@six.add_metaclass(abc.ABCMeta)
class wait_base(object):
    """Abstract base class for wait strategies."""

    @abc.abstractmethod
    def __call__(self, previous_attempt_number, delay_since_first_attempt):
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

    def __call__(self, previous_attempt_number, delay_since_first_attempt):
        return self.wait_fixed


class wait_none(wait_fixed):
    """Wait strategy that doesn't wait at all before retrying."""

    def __init__(self):
        super(wait_none, self).__init__(0)


class wait_random(wait_base):
    """Wait strategy that waits a random amount of time between min/max."""

    def __init__(self, min=0, max=1):
        self.wait_random_min = min
        self.wait_random_max = max

    def __call__(self, previous_attempt_number, delay_since_first_attempt):
        return (self.wait_random_min
                + (random.random()
                   * (self.wait_random_max - self.wait_random_min)))


class wait_combine(wait_base):
    """Combine several waiting strategies."""

    def __init__(self, *strategies):
        self.wait_funcs = strategies

    def __call__(self, previous_attempt_number, delay_since_first_attempt):
        return sum(map(
            lambda x: x(previous_attempt_number, delay_since_first_attempt),
            self.wait_funcs))


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
        self.strategies = list(strategies)

    def __call__(self, previous_attempt_number, delay_since_first_attempt):
        wait_func = self.strategies[0]
        if len(self.strategies) > 1:
            self.strategies.pop(0)
        return wait_func(previous_attempt_number, delay_since_first_attempt)


class wait_incrementing(wait_base):
    """Wait an incremental amount of time after each attempt.

    Starting at a starting value and incrementing by a value for each attempt
    (and restricting the upper limit to some maximum value).
    """

    def __init__(self, start=0, increment=100, max=_utils.MAX_WAIT):
        self.start = start
        self.increment = increment
        self.max = max

    def __call__(self, previous_attempt_number, delay_since_first_attempt):
        result = self.start + (
            self.increment * (previous_attempt_number - 1)
        )
        return max(0, min(result, self.max))


class wait_exponential(wait_base):
    """Wait strategy that applies exponential backoff.

    It allows for a customized multiplier and an ability to restrict the
    upper limit to some maximum value.
    """

    def __init__(self, multiplier=1, max=_utils.MAX_WAIT, exp_base=2):
        self.multiplier = multiplier
        self.max = max
        self.exp_base = exp_base

    def __call__(self, previous_attempt_number, delay_since_first_attempt):
        try:
            exp = self.exp_base ** previous_attempt_number
            result = self.multiplier * exp
        except OverflowError:
            return self.max
        return max(0, min(result, self.max))


class wait_full_jitter(wait_exponential):
    """Random wait with exponentially widening window.

    Wait strategy based on the results of this Amazon Architecture Blog:

    https://www.awsarchitectureblog.com/2015/03/backoff.html

    The Full Jitter strategy attempts to prevent synchronous clusters
    from forming in distributed systems by combining exponential backoff
    with random jitter. This differs from other strategies as jitter isn't
    added to the exponentially increasing sleep time, rather the time is
    computed is uniformly random between zero and the exponential point.

    Excerpted from the above blog:
        sleep = random_between(0, min(cap, base * 2 ** attempt))

    A competing algorithm called "Decorrelated Jitter" is competitive
    and in some circumstances may be better. c.f. the above blog for
    details.

    Example:
        wait_full_jitter(0.5, 60) # initial window 0.5sec, max 60sec timeout

    Optional:
        base: (float) starting jitter window size in seconds.
            Equals 'base' above.
        max_timeout_sec: (float, default 60.0) Maximum time to wait.
            Equals 'cap' above.

    Returns: (float) time to sleep in seconds
    """
    def __call__(self, previous_attempt_number, delay_since_first_attempt):
        high = super(wait_full_jitter, self).__call__(
            previous_attempt_number, delay_since_first_attempt)
        return random.uniform(0, high)
