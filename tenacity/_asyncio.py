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
try:
    from inspect import iscoroutinefunction
except ImportError:
    iscoroutinefunction = None

import sys
from asyncio import sleep

import six

from tenacity import AttemptManager, RetryAction, TryAgain
from tenacity import BaseRetrying
from tenacity import DoAttempt
from tenacity import DoSleep
from tenacity import RetryCallState


class AsyncRetrying(BaseRetrying):
    def __init__(self, sleep=sleep, **kwargs):
        super().__init__(**kwargs)
        self.sleep = sleep

    async def iter(self, retry_state):  # noqa
        fut = retry_state.outcome
        if fut is None:
            if self.before is not None:
                self.before(retry_state)
            return DoAttempt()

        is_explicit_retry = retry_state.outcome.failed and isinstance(
            retry_state.outcome.exception(), TryAgain
        )
        if iscoroutinefunction(self.retry):
            should_retry = await self.retry(retry_state=retry_state)
        else:
            should_retry = self.retry(retry_state=retry_state)
        if not (is_explicit_retry or should_retry):
            return fut.result()

        if self.after is not None:
            self.after(retry_state=retry_state)

        self.statistics["delay_since_first_attempt"] = retry_state.seconds_since_start
        if self.stop(retry_state=retry_state):
            if self.retry_error_callback:
                if iscoroutinefunction(self.retry_error_callback):
                    return await self.retry_error_callback(retry_state=retry_state)
                else:
                    return self.retry_error_callback(retry_state=retry_state)
            retry_exc = self.retry_error_cls(fut)
            if self.reraise:
                raise retry_exc.reraise()
            six.raise_from(retry_exc, fut.exception())

        if self.wait:
            iteration_sleep = self.wait(retry_state=retry_state)
        else:
            iteration_sleep = 0.0
        retry_state.next_action = RetryAction(iteration_sleep)
        retry_state.idle_for += iteration_sleep
        self.statistics["idle_for"] += iteration_sleep
        self.statistics["attempt_number"] += 1

        if self.before_sleep is not None:
            self.before_sleep(retry_state=retry_state)

        return DoSleep(iteration_sleep)

    async def __call__(self, fn, *args, **kwargs):
        self.begin(fn)

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

    def __aiter__(self):
        self.begin(None)
        self._retry_state = RetryCallState(self, fn=None, args=(), kwargs={})
        return self

    async def __anext__(self):
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

    def wraps(self, fn):
        fn = super().wraps(fn)

        # Ensure wrapper is recognized as a coroutine function.

        async def async_wrapped(*args, **kwargs):
            return await fn(*args, **kwargs)

        # Preserve attributes
        async_wrapped.retry = fn.retry
        async_wrapped.retry_with = fn.retry_with

        return async_wrapped
