# Copyright 2016 Étienne Bersac
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

import functools
import sys
import typing
from asyncio import sleep
from inspect import iscoroutinefunction

from tenacity import AttemptManager
from tenacity import BaseRetrying
from tenacity import DoAttempt
from tenacity import DoSleep
from tenacity import RetryAction
from tenacity import RetryCallState
from tenacity import TryAgain

WrappedFn = typing.TypeVar("WrappedFn", bound=typing.Callable)
_RetValT = typing.TypeVar("_RetValT")


class AsyncRetrying(BaseRetrying):
    def __init__(self, sleep: typing.Callable[[float], typing.Awaitable] = sleep, **kwargs: typing.Any) -> None:
        super().__init__(**kwargs)
        self.sleep = sleep

    async def __call__(  # type: ignore  # Change signature from supertype
        self,
        fn: typing.Callable[..., typing.Awaitable[_RetValT]],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> _RetValT:
        self.begin()

        retry_state = RetryCallState(retry_object=self, fn=fn, args=args, kwargs=kwargs)
        while True:
            do = await self.iter(retry_state=retry_state)
            if isinstance(do, DoAttempt):
                try:
                    result = await fn(*args, **kwargs)
                except BaseException:  # noqa: B902
                    retry_state.set_exception(sys.exc_info())
                else:
                    retry_state.set_result(result)
            elif isinstance(do, DoSleep):
                retry_state.prepare_for_next_attempt()
                await self.sleep(do)
            else:
                return do

    def __aiter__(self) -> "AsyncRetrying":
        self.begin()
        self._retry_state = RetryCallState(self, fn=None, args=(), kwargs={})
        return self

    async def __anext__(self) -> typing.Union[AttemptManager, typing.Any]:
        while True:
            do = await self.iter(retry_state=self._retry_state)
            if do is None:
                raise StopAsyncIteration
            elif isinstance(do, DoAttempt):
                return AttemptManager(retry_state=self._retry_state)
            elif isinstance(do, DoSleep):
                self._retry_state.prepare_for_next_attempt()
                await self.sleep(do)
            else:
                return do

    def wraps(self, fn: WrappedFn) -> WrappedFn:
        fn = super().wraps(fn)
        # Ensure wrapper is recognized as a coroutine function.

        @functools.wraps(fn)
        async def async_wrapped(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
            return await fn(*args, **kwargs)

        # Preserve attributes
        async_wrapped.retry = fn.retry
        async_wrapped.retry_with = fn.retry_with

        return async_wrapped

    @staticmethod
    async def handle_custom_function(
        func: typing.Union[typing.Callable, typing.Awaitable], retry_state: RetryCallState
    ) -> typing.Any:
        if iscoroutinefunction(func):
            return await func(retry_state)
        return func(retry_state)

    async def iter(self, retry_state: "RetryCallState") -> typing.Union[DoAttempt, DoSleep, typing.Any]:  # noqa
        fut = retry_state.outcome
        if fut is None:
            if self.before is not None:
                await self.handle_custom_function(self.before, retry_state)
            return DoAttempt()

        is_explicit_retry = retry_state.outcome.failed and isinstance(retry_state.outcome.exception(), TryAgain)
        if not (is_explicit_retry or self.retry(retry_state=retry_state)):
            return fut.result()

        if self.after is not None:
            await self.handle_custom_function(self.after, retry_state)

        self.statistics["delay_since_first_attempt"] = retry_state.seconds_since_start
        if self.stop(retry_state=retry_state):
            if self.retry_error_callback:
                return await self.handle_custom_function(self.retry_error_callback, retry_state)
            retry_exc = self.retry_error_cls(fut)
            if self.reraise:
                raise retry_exc.reraise()
            raise retry_exc from fut.exception()

        if self.wait:
            _sleep = await self.handle_custom_function(self.wait, retry_state=retry_state)
        else:
            _sleep = 0.0
        retry_state.next_action = RetryAction(_sleep)
        retry_state.idle_for += _sleep
        self.statistics["idle_for"] += _sleep
        self.statistics["attempt_number"] += 1

        if self.before_sleep is not None:
            await self.handle_custom_function(self.before_sleep, retry_state)

        return DoSleep(_sleep)
