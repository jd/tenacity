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

import asyncio
import sys

import six
from contextlib

from tenacity import BaseRetrying
from tenacity import DoAttempt
from tenacity import DoSleep
from tenacity import NO_RESULT


class AsyncRetrying(BaseRetrying):
    @asyncio.coroutine
    def call(self, fn, *args, **kwargs):
        self.begin(fn)

        result = NO_RESULT
        exc_info = None

        while True:
            do = self.iter(result=result, exc_info=exc_info)
            if isinstance(do, DoAttempt):
                try:
                    result = yield from fn(*args, **kwargs)
                    exc_info = None
                    continue
                except Exception:
                    result = NO_RESULT
                    exc_info = sys.exc_info()
                    continue
            elif isinstance(do, DoSleep):
                result = NO_RESULT
                exc_info = None
                yield from asyncio.sleep(do)
            else:
                return do
          
class AsyncRetryingContext(AsyncRetrying):
    """A classic context manager is NOT able to suspend execution in its enter and exit methods."""

    def __init__(self, f, **kwargs):
        super(AsyncRetryingContext, self).__init__(**kwargs)
        self.f = f if asyncio.iscoroutinefunction(f) else asyncio.coroutine(f)

    def __enter__(self):
        r = self
        f = self.f

        @six.wraps(f)
        def wrapped_f(*args, **kw):
            return _AsyncContextManager(r.call, ((f,) + args), kw)

        wrapped_f.retry = r
        return wrapped_f

    def __exit__(self, exc_type, exc_val, exc_tb):
        # If we returned True here, any exception inside the with block would be suppressed!
        return False

    
class _AsyncContextManager(contextlib._GeneratorContextManager):
    async def __aenter__(self):
        try:
            return await self.gen.__anext__()
        except StopAsyncIteration as e:
            raise RuntimeError("async generator didn't yield") from None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            try:
                await self.gen.__anext__()
            except StopAsyncIteration:
                return
            else:
                raise RuntimeError("async generator didn't stop")
        else:
            if exc_val is None:
                exc_val = exc_type()
            try:
                await self.gen.athrow(exc_type, exc_val, exc_tb)
                raise RuntimeError("async generator didn't stop after throw()")
            except StopAsyncIteration as exc:
                return exc is not exc_val
            except RuntimeError as exc:
                if exc is exc_val:
                    return False
                if exc.__cause__ is exc_val:
                    return False
                raise
            except:
                if sys.exc_info()[1] is not exc_val:
                    raise
