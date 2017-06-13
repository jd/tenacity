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

def fn(x): 
    """Creates a thunk"""
    if callable(x):
        return x
    else:
        return lambda atmpt_ct, delay: x    

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
        self.wait_fixed = fn(wait)

    def __call__(self, previous_attempt_number, delay_since_first_attempt):
        return self.wait_fixed(previous_attempt_number, delay_since_first_attempt)


class wait_none(wait_fixed):
    """Wait strategy that doesn't wait at all before retrying."""

    def __init__(self):
        super(wait_none, self).__init__(0)


class wait_random(wait_base):
    """Wait strategy that waits a random amount of time between min/max."""

    def __init__(self, min=0, max=1):
        self.wait_random_min = fn(min)
        self.wait_random_max = fn(max)

    def __call__(self, previous_attempt_number, delay_since_first_attempt):
        wait_min = self.wait_random_min(previous_attempt_number, delay_since_first_attempt)
        wait_max = self.wait_random_max(previous_attempt_number, delay_since_first_attempt)
        return random.uniform(wait_min, wait_max)

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
        self.start = fn(start)
        self.increment = fn(increment)
        self.max = fn(max)

    def __call__(self, previous_attempt_number, delay_since_first_attempt):
        start = self.start(previous_attempt_number, delay_since_first_attempt)
        incr = self.increment(previous_attempt_number, delay_since_first_attempt)
        end = self.max(previous_attempt_number, delay_since_first_attempt)

        result = start + (
            incr * (previous_attempt_number - 1)
        )
        return max(0, min(result, end))

class wait_exponential(wait_base):
    """Wait strategy that applies exponential backoff.

    It allows for a customized multiplier and an ability to restrict the
    upper limit to some maximum value.
    """

    def __init__(self, multiplier=1, max=_utils.MAX_WAIT, exp_base=2):
        self.multiplier = fn(multiplier)
        self.max = fn(max)
        self.exp_base = fn(exp_base)

    def __call__(self, previous_attempt_number, delay_since_first_attempt):
        exp_base = self.exp_base(previous_attempt_number, delay_since_first_attempt) 
        multiplier = self.multiplier(previous_attempt_number, delay_since_first_attempt)
        ceil = self.max(previous_attempt_number, delay_since_first_attempt)
        try:
            exp = exp_base ** previous_attempt_number
            result = multiplier * exp
        except OverflowError:
            return ceil
        return max(0, min(result, ceil))

def wait_full_jitter(base=0.5, cap=60):
    assert base >= 0
    assert cap >= 0
    return wait_random(0, wait_exponential(base, cap))
