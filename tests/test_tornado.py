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
from collections.abc import Generator
from typing import Any
from unittest import mock

from tornado import gen, testing

import tenacity
from tenacity import RetryError, retry, stop_after_attempt, tornadoweb

from .test_tenacity import NoIOErrorAfterCount


@retry
@gen.coroutine
def _retryable_coroutine(thing: NoIOErrorAfterCount) -> Generator[Any, Any, None]:
    yield gen.sleep(0.00001)
    thing.go()


@retry(stop=stop_after_attempt(2))
@gen.coroutine
def _retryable_coroutine_with_2_attempts(
    thing: NoIOErrorAfterCount,
) -> Generator[Any, Any, None]:
    yield gen.sleep(0.00001)
    thing.go()


class TestTornado(testing.AsyncTestCase):
    @testing.gen_test
    def test_retry(self) -> Generator[Any, Any, None]:
        assert gen.is_coroutine_function(_retryable_coroutine)
        thing = NoIOErrorAfterCount(5)
        yield _retryable_coroutine(thing)
        assert thing.counter == thing.count

    @testing.gen_test
    def test_stop_after_attempt(self) -> Generator[Any, Any, None]:
        assert gen.is_coroutine_function(_retryable_coroutine)
        thing = NoIOErrorAfterCount(2)
        try:
            yield _retryable_coroutine_with_2_attempts(thing)
        except RetryError:
            assert thing.counter == 2

    @testing.gen_test
    def test_disabled_call_returns_result_without_callbacks(
        self,
    ) -> Generator[Any, Any, None]:
        before = mock.Mock()
        result = object()

        @gen.coroutine
        def work() -> Generator[Any, Any, Any]:
            yield gen.moment
            return result

        retrying = tornadoweb.TornadoRetrying(enabled=False, before=before)
        actual = yield retrying(work)

        assert actual is result
        before.assert_not_called()
        assert retrying.statistics == {}

    @testing.gen_test
    def test_disabled_call_propagates_original_exception(
        self,
    ) -> Generator[Any, Any, None]:
        calls = 0
        error = ValueError("unavailable")

        @gen.coroutine
        def work() -> Generator[Any, Any, None]:
            nonlocal calls
            calls += 1
            yield gen.moment
            raise error

        retrying = tornadoweb.TornadoRetrying(enabled=False, stop=stop_after_attempt(2))
        with self.assertRaises(ValueError) as caught:
            yield retrying(work)

        assert caught.exception is error
        assert calls == 1

    def test_repr(self) -> None:
        repr(tornadoweb.TornadoRetrying())

    def test_old_tornado(self) -> None:
        old_attr = gen.is_coroutine_function
        try:
            del gen.is_coroutine_function

            # is_coroutine_function was introduced in tornado 4.5;
            # verify that we don't *completely* fall over on old versions
            @retry
            def retryable(thing: NoIOErrorAfterCount) -> None:
                pass

        finally:
            gen.is_coroutine_function = old_attr

    def test_tornado_set_to_none(self) -> None:
        # Forcing the non-tornado path by nulling the module global is how
        # downstream suites exercise installs without tornado.
        with mock.patch.object(tenacity, "tornado", None):

            @retry(stop=stop_after_attempt(1))
            def retryable() -> int:
                return 1

            assert retryable() == 1


if __name__ == "__main__":
    unittest.main()
