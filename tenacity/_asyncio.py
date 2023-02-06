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

from tenacity import AttemptManager
from tenacity import BaseRetrying
from tenacity import DoAttempt
from tenacity import DoSleep
from tenacity import RetryCallState


WrappedFn = typing.TypeVar("WrappedFn", bound=typing.Callable[..., typing.Any])
_RetValT = typing.TypeVar("_RetValT")


class AsyncRetrying(BaseRetrying):
    def __init__(
        self, sleep: typing.Callable[[float], typing.Awaitable[typing.Any]] = sleep, **kwargs: typing.Any
    ) -> None:
        super().__init__(**kwargs)
        self.sleep = sleep

    async def __call__(  # type: ignore[override]
        self,
        fn: typing.Callable[..., typing.Awaitable[_RetValT]],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> _RetValT:
        self.begin()

        retry_state = RetryCallState(retry_object=self, fn=fn, args=args, kwargs=kwargs)
        while True:
            do = self.iter(retry_state=retry_state)
            if isinstance(do, DoAttempt):
                try:
                    result = await fn(*args, **kwargs)
                except BaseException:  # noqa: B902
                    retry_state.set_exception(sys.exc_info())  # type: ignore[arg-type]
                else:
                    retry_state.set_result(result)
            elif isinstance(do, DoSleep):
                retry_state.prepare_for_next_attempt()
                await self.sleep(do)
            else:
                return do  # type: ignore[no-any-return]

    def __iter__(self) -> typing.Generator[AttemptManager, None, None]:
        raise TypeError("AsyncRetrying object is not iterable")

    def __aiter__(self) -> "AsyncRetrying":
        self.begin()
        self._retry_state = RetryCallState(self, fn=None, args=(), kwargs={})
        return self

    async def __anext__(self) -> AttemptManager:
        while True:
            do = self.iter(retry_state=self._retry_state)
            if do is None:
                raise StopAsyncIteration
            elif isinstance(do, DoAttempt):
                return AttemptManager(retry_state=self._retry_state)
            elif isinstance(do, DoSleep):
                self._retry_state.prepare_for_next_attempt()
                await self.sleep(do)
            else:
                raise StopAsyncIteration

    def wraps(self, fn: WrappedFn) -> WrappedFn:
        fn = super().wraps(fn)
        # Ensure wrapper is recognized as a coroutine function.

        @functools.wraps(fn)
        async def async_wrapped(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
            return await fn(*args, **kwargs)

        # Preserve attributes
        async_wrapped.retry = fn.retry  # type: ignore[attr-defined]
        async_wrapped.retry_with = fn.retry_with  # type: ignore[attr-defined]

        return async_wrapped  # type: ignore[return-value]
