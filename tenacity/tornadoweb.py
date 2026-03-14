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

import inspect
import sys
import typing

import tenacity
from tenacity import BaseRetrying
from tenacity import DoAttempt
from tenacity import DoSleep
from tenacity import RetryCallState

from tornado import gen

if typing.TYPE_CHECKING:
    from tornado.concurrent import Future

_RetValT = typing.TypeVar("_RetValT")


class TornadoRetrying(BaseRetrying):
    def __init__(
        self,
        sleep: "typing.Union[typing.Callable[[float], Future[None]], object]" = tenacity._unset,
        **kwargs: typing.Any,
    ) -> None:
        if sleep is tenacity._unset:
            sleep = gen.sleep
        super().__init__(sleep=sleep, **kwargs)

    @staticmethod
    def _is_awaitable(value: typing.Any) -> bool:
        return gen.is_future(value) or inspect.isawaitable(value)

    @staticmethod
    def _convert_awaitable(value: typing.Any) -> typing.Any:
        if gen.is_future(value) or inspect.isawaitable(value):
            return gen.convert_yielded(value)
        return value

    @gen.coroutine  # type: ignore[untyped-decorator]
    def _resolve_awaitable(
        self, value: typing.Any
    ) -> "typing.Generator[typing.Any, typing.Any, typing.Any]":
        while self._is_awaitable(value):
            value = yield self._convert_awaitable(value)
        raise gen.Return(value)

    @gen.coroutine  # type: ignore[untyped-decorator]
    def _run_retry(
        self, retry_state: "RetryCallState"
    ) -> "typing.Generator[typing.Any, typing.Any, None]":  # type: ignore[override]
        retry_result = self.retry(retry_state)
        retry_result = yield self._resolve_awaitable(retry_result)
        self.iter_state.retry_run_result = retry_result

    @gen.coroutine  # type: ignore[untyped-decorator]
    def _run_wait(self, retry_state: "RetryCallState") -> "typing.Generator[typing.Any, typing.Any, None]":  # type: ignore[override]
        if self.wait:
            sleep = self.wait(retry_state)
            sleep = yield self._resolve_awaitable(sleep)
        else:
            sleep = 0.0
        retry_state.upcoming_sleep = sleep

    @gen.coroutine  # type: ignore[untyped-decorator]
    def _run_stop(
        self, retry_state: "RetryCallState"
    ) -> "typing.Generator[typing.Any, typing.Any, None]":  # type: ignore[override]
        self.statistics["delay_since_first_attempt"] = retry_state.seconds_since_start
        stop_result = self.stop(retry_state)
        stop_result = yield self._resolve_awaitable(stop_result)
        self.iter_state.stop_run_result = stop_result

    @gen.coroutine  # type: ignore[untyped-decorator]
    def iter(  # type: ignore[override]
        self, retry_state: "RetryCallState"
    ) -> "typing.Generator[typing.Any, typing.Any, typing.Any]":
        self._begin_iter(retry_state)
        result = None
        for action in self.iter_state.actions:
            result = yield self._resolve_awaitable(action(retry_state))
        raise gen.Return(result)

    @gen.coroutine  # type: ignore[untyped-decorator]
    def __call__(
        self,
        fn: "typing.Callable[..., typing.Union[typing.Generator[typing.Any, typing.Any, _RetValT], Future[_RetValT]]]",
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> "typing.Generator[typing.Any, typing.Any, _RetValT]":
        self.begin()

        retry_state = RetryCallState(retry_object=self, fn=fn, args=args, kwargs=kwargs)
        while True:
            do = yield self.iter(retry_state=retry_state)
            if isinstance(do, DoAttempt):
                try:
                    result = yield fn(*args, **kwargs)
                except BaseException:  # noqa: B902
                    retry_state.set_exception(sys.exc_info())  # type: ignore[arg-type]
                else:
                    retry_state.set_result(result)
            elif isinstance(do, DoSleep):
                retry_state.prepare_for_next_attempt()
                if self.sleep is not None:
                    sleep_result = self.sleep(do)
                    yield self._resolve_awaitable(sleep_result)
            else:
                raise gen.Return(do)
