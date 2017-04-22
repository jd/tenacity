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
  """An asynchronous context manager is a context manager that is able to suspend execution in its enter and exit methods."""

  def __init__(self, f, **kwargs):
    super(AsyncRetryingContext, self).__init__(**kwargs)
    self.fn = f if asyncio.iscoroutinefunction(f) else asyncio.coroutine(f)
    self.args = None
    self.kwargs = None
    self.inner_context = None

  def __call__(self, *args, **kwargs):
    self.args = args
    self.kwargs = kwargs
    return self

  @asyncio.coroutine
  def __aenter__(self):
    result = yield from self.call(self.fn, *self.args, **self.kwargs)

    # Check if result object is a context manager (e.g. with open(filename) as f)
    if getattr(result, '__aenter__', None):
      self.inner_context = result
      return (yield from result.__aenter__())
    elif getattr(result, '__enter__', None):
      self.inner_context = result
      return result.__enter__()
    else:
      return result

  @asyncio.coroutine
  def __aexit__(self, exc_type, exc_val, exc_tb):
    # If we returned True here, any exception inside the with block would be suppressed!
    if self.inner_context:
      if getattr(self.inner_context, '__aexit__', None):
        self.inner_context.__aexit__(exc_type, exc_val, exc_tb)
      elif getattr(self.inner_context, '__exit__', None):
        self.inner_context.__exit__(exc_type, exc_val, exc_tb)
