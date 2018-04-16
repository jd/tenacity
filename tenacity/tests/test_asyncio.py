# coding: utf-8
# Copyright 2016 Étienne Bersac
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
import unittest

import six

from tenacity import _asyncio as tasyncio
from tenacity import retry
from tenacity.tests.test_tenacity import NoIOErrorAfterCount


def asynctest(callable_):
    callable_ = asyncio.coroutine(callable_)

    @six.wraps(callable_)
    def wrapper(*a, **kw):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(callable_(*a, **kw))

    return wrapper


@retry
@asyncio.coroutine
def _retryable_coroutine(thing):
    yield from asyncio.sleep(0.00001)
    thing.go()


class TestAsync(unittest.TestCase):
    @asynctest
    def test_retry(self):
        assert asyncio.iscoroutinefunction(_retryable_coroutine)
        thing = NoIOErrorAfterCount(5)
        yield from _retryable_coroutine(thing)
        assert thing.counter == thing.count

    def test_repr(self):
        repr(tasyncio.AsyncRetrying())


if __name__ == '__main__':
    unittest.main()
