# coding: utf-8
# Copyright 2017 Elisey Zanko
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

import unittest

from tenacity import RetryError, retry, stop_after_attempt
from tenacity import tornadoweb

from tornado import gen
from tornado import testing

from .test_tenacity import NoIOErrorAfterCount


@retry
@gen.coroutine
def _retryable_coroutine(thing):
    yield gen.sleep(0.00001)
    thing.go()


@retry(stop=stop_after_attempt(2))
@gen.coroutine
def _retryable_coroutine_with_2_attempts(thing):
    yield gen.sleep(0.00001)
    thing.go()


class TestTornado(testing.AsyncTestCase):
    @testing.gen_test
    def test_retry(self):
        assert gen.is_coroutine_function(_retryable_coroutine)
        thing = NoIOErrorAfterCount(5)
        yield _retryable_coroutine(thing)
        assert thing.counter == thing.count

    @testing.gen_test
    def test_stop_after_attempt(self):
        assert gen.is_coroutine_function(_retryable_coroutine)
        thing = NoIOErrorAfterCount(2)
        try:
            yield _retryable_coroutine_with_2_attempts(thing)
        except RetryError:
            assert thing.counter == 2

    def test_repr(self):
        repr(tornadoweb.TornadoRetrying())

    def test_old_tornado(self):
        old_attr = gen.is_coroutine_function
        try:
            del gen.is_coroutine_function

            # is_coroutine_function was introduced in tornado 4.5;
            # verify that we don't *completely* fall over on old versions
            @retry
            def retryable(thing):
                pass

        finally:
            gen.is_coroutine_function = old_attr


if __name__ == "__main__":
    unittest.main()
