# -*- coding: utf-8 -*-
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
import sys

from tenacity import AttemptManager
from tenacity import BaseRetrying
from tenacity import DoAttempt
from tenacity import DoSleep
from tenacity import RetryCallState


async def _portable_async_sleep(seconds):
    # If trio is already imported, then importing it is cheap.
    # If trio isn't already imported, then it's definitely not running, so we
    # can skip further checks.
    if "trio" in sys.modules:
        # If trio is available, then sniffio is too
        import trio, sniffio
        if sniffio.current_async_library() == "trio":
            await trio.sleep(seconds)
            return
    # Otherwise, assume asyncio
    import asyncio
    await asyncio.sleep(seconds)


class AsyncRetrying(BaseRetrying):
    def __init__(self, sleep=_portable_async_sleep, **kwargs):
        super(AsyncRetrying, self).__init__(**kwargs)
        self.sleep = sleep

    async def __call__(self, fn, *args, **kwargs):
        self.begin(fn)

        retry_state = RetryCallState(retry_object=self, fn=fn, args=args, kwargs=kwargs)
        while True:
            do = self.iter(retry_state=retry_state)
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

    def __aiter__(self):
        self.begin(None)
        self._retry_state = RetryCallState(self, fn=None, args=(), kwargs={})
        return self

    async def __anext__(self):
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
                return do

    def wraps(self, fn):
        fn = super().wraps(fn)
        # Ensure wrapper is recognized as a coroutine function.

        async def async_wrapped(*args, **kwargs):
            return await fn(*args, **kwargs)

        # Preserve attributes
        async_wrapped.retry = fn.retry
        async_wrapped.retry_with = fn.retry_with

        return async_wrapped
