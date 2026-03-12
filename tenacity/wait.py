# Copyright 2016–2021 Julien Danjou
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
import typing
import warnings

from tenacity import _utils

if typing.TYPE_CHECKING:
    from tenacity import RetryCallState


class wait_base(abc.ABC):
    """Abstract base class for wait strategies."""

    @abc.abstractmethod
    def __call__(self, retry_state: "RetryCallState") -> float:
        pass

    def __add__(self, other: "wait_base") -> "wait_combine":
        return wait_combine(self, other)

    def __radd__(self, other: "wait_base") -> "wait_combine | wait_base":
        # make it possible to use multiple waits with the built-in sum function
        if other == 0:  # type: ignore[comparison-overlap]
            return self
        return self.__add__(other)


WaitBaseT = wait_base | typing.Callable[["RetryCallState"], float | int]


class wait_fixed(wait_base):
    """Wait strategy that waits a fixed amount of time between each retry."""

    def __init__(self, wait: _utils.time_unit_type) -> None:
        self.wait_fixed = _utils.to_seconds(wait)

    def __call__(self, retry_state: "RetryCallState") -> float:
        return self.wait_fixed


class wait_none(wait_fixed):
    """Wait strategy that doesn't wait at all before retrying."""

    def __init__(self) -> None:
        super().__init__(0)


class wait_random(wait_base):
    """Wait strategy that waits a random amount of time between min/max."""

    def __init__(
        self, min: _utils.time_unit_type = 0, max: _utils.time_unit_type = 1
    ) -> None:
        self.wait_random_min = _utils.to_seconds(min)
        self.wait_random_max = _utils.to_seconds(max)

    def __call__(self, retry_state: "RetryCallState") -> float:
        return self.wait_random_min + (
            random.random() * (self.wait_random_max - self.wait_random_min)
        )


class wait_combine(wait_base):
    """Combine several waiting strategies."""

    def __init__(self, *strategies: wait_base) -> None:
        self.wait_funcs = strategies

    def __call__(self, retry_state: "RetryCallState") -> float:
        return sum(x(retry_state=retry_state) for x in self.wait_funcs)


class wait_chain(wait_base):
    """Chain two or more waiting strategies.

    If all strategies are exhausted, the very last strategy is used
    thereafter.

    For example::

        @retry(wait=wait_chain(*[wait_fixed(1) for i in range(3)] +
                               [wait_fixed(2) for j in range(5)] +
                               [wait_fixed(5) for k in range(4)]))
        def wait_chained():
            print("Wait 1s for 3 attempts, 2s for 5 attempts and 5s "
                  "thereafter.")
    """

    def __init__(self, *strategies: wait_base) -> None:
        self.strategies = strategies

    def __call__(self, retry_state: "RetryCallState") -> float:
        wait_func_no = min(max(retry_state.attempt_number, 1), len(self.strategies))
        wait_func = self.strategies[wait_func_no - 1]
        return wait_func(retry_state=retry_state)


class wait_exception(wait_base):
    """Wait strategy that waits the amount of time returned by the predicate.

    The predicate is passed the exception object. Based on the exception, the
    user can decide how much time to wait before retrying.

    For example::

        def http_error(exception: BaseException) -> float:
            if (
                isinstance(exception, requests.HTTPError)
                and exception.response.status_code == requests.codes.too_many_requests
            ):
                return float(exception.response.headers.get("Retry-After", "1"))
            return 60.0


        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exception(http_error),
        )
        def http_get_request(url: str) -> None:
            response = requests.get(url)
            response.raise_for_status()
    """

    def __init__(self, predicate: typing.Callable[[BaseException], float]) -> None:
        self.predicate = predicate

    def __call__(self, retry_state: "RetryCallState") -> float:
        if retry_state.outcome is None:
            raise RuntimeError("__call__() called before outcome was set")

        exception = retry_state.outcome.exception()
        if exception is None:
            raise RuntimeError("outcome failed but the exception is None")
        return self.predicate(exception)


class wait_incrementing(wait_base):
    """Wait an incremental amount of time after each attempt.

    Starting at a starting value and incrementing by a value for each attempt
    (and restricting the upper limit to some maximum value).
    """

    def __init__(
        self,
        start: _utils.time_unit_type = 0,
        increment: _utils.time_unit_type = 100,
        max: _utils.time_unit_type = _utils.MAX_WAIT,
    ) -> None:
        self.start = _utils.to_seconds(start)
        self.increment = _utils.to_seconds(increment)
        self.max = _utils.to_seconds(max)

    def __call__(self, retry_state: "RetryCallState") -> float:
        result = self.start + (self.increment * (retry_state.attempt_number - 1))
        return max(0, min(result, self.max))


class wait_exponential(wait_base):
    """Wait strategy that applies exponential backoff.

    It allows for a customized multiplier and an ability to restrict the
    upper and lower limits to some maximum and minimum value.

    The intervals are fixed (i.e. there is no jitter), so this strategy is
    suitable for balancing retries against latency when a required resource is
    unavailable for an unknown duration, but *not* suitable for resolving
    contention between multiple processes for a shared resource. Use
    wait_random_exponential for the latter case.
    """

    def __init__(
        self,
        multiplier: float = 1,
        max: _utils.time_unit_type = _utils.MAX_WAIT,
        exp_base: float = 2,
        min: _utils.time_unit_type = 0,
    ) -> None:
        self.multiplier = multiplier
        self.min = _utils.to_seconds(min)
        self.max = _utils.to_seconds(max)
        self.exp_base = exp_base

    def __call__(self, retry_state: "RetryCallState") -> float:
        try:
            exp = self.exp_base ** (retry_state.attempt_number - 1)
            result = self.multiplier * exp
        except OverflowError:
            return self.max
        return max(max(0, self.min), min(result, self.max))


class wait_fibonacci(wait_base):
    """Wait strategy that applies a Fibonacci backoff.

    Fibonacci backoff is a compromise between linear and exponential backoff.
    It increases the wait time more slowly than a pure exponential strategy,
    making it effective for scenarios where a resource might be unavailable
    for a moderate duration and you want to minimize latency without
    hammering the server.

    .. note::
        This strategy is stateful. The wait intervals increase with each
        subsequent retry performed by this specific instance.

    Example::

        # Wait times: 1s, 2s, 3s, 5s, 8s, 13s... up to 60s
        wait_fibonacci(max=60)
    """

    def __init__(
        self,
        max: _utils.time_unit_type = _utils.MAX_WAIT,
    ) -> None:
        """Initialize the wait strategy.

        :param max: The maximum number of seconds to wait.
        """
        self.max = _utils.to_seconds(max)
        self._serie = [0, 1]

    def compute_next_value(self) -> int:
        """Compute the next value in the Fibonacci sequence."""
        next_value = self._serie[-1] + self._serie[-2]
        self._serie.append(next_value)
        return next_value

    def __call__(self, retry_state: "RetryCallState") -> float:
        """Return the next wait time from the Fibonacci sequence."""
        try:
            result = self.compute_next_value()
        except OverflowError:
            return self.max
        return min(result, self.max)


class wait_random_exponential(wait_exponential):
    """Random wait with exponentially widening window.

    An exponential backoff strategy used to mediate contention between multiple
    uncoordinated processes for a shared resource in distributed systems. This
    is the sense in which "exponential backoff" is meant in e.g. Ethernet
    networking, and corresponds to the "Full Jitter" algorithm described in
    this blog post:

    https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

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

    def __call__(self, retry_state: "RetryCallState") -> float:
        high = super().__call__(retry_state=retry_state)
        return random.uniform(self.min, high)


class wait_exponential_jitter(wait_base):
    """Wait strategy that applies exponential backoff and jitter.

    It allows for a customized multiplier, maximum wait, jitter and minimum.

    This implements the strategy described here:
    https://cloud.google.com/storage/docs/retry-strategy

    The wait time is max(min, min(multiplier * 2**n + random.uniform(0, jitter), maximum))
    where n is the retry count.
    """

    def __init__(
        self,
        initial: float = 1,
        max: _utils.time_unit_type = _utils.MAX_WAIT,
        exp_base: float = 2,
        jitter: _utils.time_unit_type = 1,
        min: _utils.time_unit_type = 0,
        multiplier: float = 1,
    ) -> None:
        if initial != 1 and multiplier != 1:
            raise ValueError(
                "Cannot specify both 'initial' and 'multiplier' — use 'multiplier' only"
            )

        if initial != 1:
            warnings.warn(
                "The 'initial' parameter is deprecated, use 'multiplier' instead",
                DeprecationWarning,
                stacklevel=2,
            )
            multiplier = initial

        self.multiplier = multiplier
        self.max = _utils.to_seconds(max)
        self.exp_base = exp_base
        self.jitter = _utils.to_seconds(jitter)
        self.min = _utils.to_seconds(min)

    def __call__(self, retry_state: "RetryCallState") -> float:
        jitter = random.uniform(0, self.jitter)
        try:
            exp = self.exp_base ** (retry_state.attempt_number - 1)
            result = self.multiplier * exp + jitter
        except OverflowError:
            result = self.max
        return max(max(0, self.min), min(result, self.max))
