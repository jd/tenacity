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
import typing

from tenacity import _utils
from tenacity.stop import stop_base

if typing.TYPE_CHECKING:
    import asyncio

    from tenacity import RetryCallState


class stop_any(stop_base):
    """Stop if any of the stop condition is valid."""

    def __init__(self, *stops: stop_base) -> None:
        self.stops = stops

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        return any(x(retry_state) for x in self.stops)


class stop_all(stop_base):
    """Stop if all the stop conditions are valid."""

    def __init__(self, *stops: stop_base) -> None:
        self.stops = stops

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        return all(x(retry_state) for x in self.stops)


class _stop_never(stop_base):
    """Never stop."""

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        return False


stop_never = _stop_never()


class stop_when_event_set(stop_base):
    """Stop when the given event is set."""

    def __init__(self, event: "asyncio.Event") -> None:
        self.event = event

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        return self.event.is_set()


class stop_after_attempt(stop_base):
    """Stop when the previous attempt >= max_attempt."""

    def __init__(self, max_attempt_number: int) -> None:
        self.max_attempt_number = max_attempt_number

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        return retry_state.attempt_number >= self.max_attempt_number


class stop_after_delay(stop_base):
    """
    Stop when the time from the first attempt >= limit.

    Note: `max_delay` will be exceeded, so when used with a `wait`, the actual total delay will be greater
    than `max_delay` by some of the final sleep period before `max_delay` is exceeded.

    If you need stricter timing with waits, consider `stop_before_delay` instead.
    """

    def __init__(self, max_delay: _utils.time_unit_type) -> None:
        self.max_delay = _utils.to_seconds(max_delay)

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        if retry_state.seconds_since_start is None:
            raise RuntimeError("__call__() called but seconds_since_start is not set")
        return retry_state.seconds_since_start >= self.max_delay


class stop_before_delay(stop_base):
    """
    Stop right before the next attempt would take place after the time from the first attempt >= limit.

    Most useful when you are using with a `wait` function like wait_random_exponential, but need to make
    sure that the max_delay is not exceeded.
    """

    def __init__(self, max_delay: _utils.time_unit_type) -> None:
        self.max_delay = _utils.to_seconds(max_delay)

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        if retry_state.seconds_since_start is None:
            raise RuntimeError("__call__() called but seconds_since_start is not set")
        return retry_state.seconds_since_start + retry_state.upcoming_sleep >= self.max_delay
