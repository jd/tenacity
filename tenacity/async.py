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
import six
import sys

from tenacity import BaseRetrying
from tenacity import DoAttempt
from tenacity import DoSleep
from tenacity import NO_RESULT


class AsyncRetrying(BaseRetrying):
    def __init__(self,
                 fn=None,
                 **kwargs):
        super(AsyncRetrying, self).__init__(**kwargs)
        self.fn = (fn if asyncio.iscoroutinefunction(fn)
                   else asyncio.coroutine(fn))

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

    def context(self, fn):
        self.fn = (fn if asyncio.iscoroutinefunction(fn)
                   else asyncio.coroutine(fn))
        return self

    def __enter__(self):
        # A synchronous context manager is NOT able to suspend
        # execution in its enter and exit methods.
        if not self.fn:
            return

        r = self
        f = self.fn

        @six.wraps(f)
        def wrapped_f(*args, **kw):
            return r.call(f, *args, **kw)

        wrapped_f.retry = r
        return wrapped_f

    def __exit__(self, exc_type, exc_val, exc_tb):
        return
