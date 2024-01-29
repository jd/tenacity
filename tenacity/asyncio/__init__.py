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
import functools
import inspect
import sys
import typing as t

from tenacity import AttemptManager
from tenacity import BaseRetrying
from tenacity import DoAttempt
from tenacity import DoSleep
from tenacity import RetryCallState
from tenacity import RetryError
from tenacity import after_nothing
from tenacity import before_nothing

# Import all built-in retry strategies for easier usage.
from .retry import RetryBaseT
from .retry import retry_all  # noqa
from .retry import retry_always  # noqa
from .retry import retry_any  # noqa
from .retry import retry_if_exception  # noqa
from .retry import retry_if_exception_type  # noqa
from .retry import retry_if_exception_cause_type  # noqa
from .retry import retry_if_not_exception_type  # noqa
from .retry import retry_if_not_result  # noqa
from .retry import retry_if_result  # noqa
from .retry import retry_never  # noqa
from .retry import retry_unless_exception_type  # noqa
from .retry import retry_if_exception_message  # noqa
from .retry import retry_if_not_exception_message  # noqa
# Import all built-in stop strategies for easier usage.
from .stop import StopBaseT
from .stop import stop_after_attempt  # noqa
from .stop import stop_after_delay  # noqa
from .stop import stop_before_delay  # noqa
from .stop import stop_all  # noqa
from .stop import stop_any  # noqa
from .stop import stop_never  # noqa
from .stop import stop_when_event_set  # noqa
# Import all built-in wait strategies for easier usage.
from .wait import WaitBaseT
from .wait import wait_chain  # noqa
from .wait import wait_combine  # noqa
from .wait import wait_exponential  # noqa
from .wait import wait_fixed  # noqa
from .wait import wait_incrementing  # noqa
from .wait import wait_none  # noqa
from .wait import wait_random  # noqa
from .wait import wait_random_exponential  # noqa
from .wait import wait_random_exponential as wait_full_jitter  # noqa
from .wait import wait_exponential_jitter  # noqa

WrappedFnReturnT = t.TypeVar("WrappedFnReturnT")
WrappedFn = t.TypeVar("WrappedFn", bound=t.Callable[..., t.Awaitable[t.Any]])


def _is_coroutine_callable(call: t.Callable[..., t.Any]) -> bool:
    if inspect.isroutine(call):
        return inspect.iscoroutinefunction(call)
    if inspect.isclass(call):
        return False
    dunder_call = getattr(call, "__call__", None)  # noqa: B004
    return inspect.iscoroutinefunction(dunder_call)


class AsyncRetrying(BaseRetrying):
    def __init__(
        self,
        sleep: t.Callable[[t.Union[int, float]], t.Union[None, t.Awaitable[None]]] = asyncio.sleep,
        stop: "t.Union[StopBaseT, StopBaseT]" = stop_never,
        wait: "t.Union[WaitBaseT, WaitBaseT]" = wait_none(),
        retry: "t.Union[RetryBaseT, RetryBaseT]" = retry_if_exception_type(),
        before: t.Callable[["RetryCallState"], t.Union[None, t.Awaitable[None]]] = before_nothing,
        after: t.Callable[["RetryCallState"], t.Union[None, t.Awaitable[None]]] = after_nothing,
        before_sleep: t.Optional[t.Callable[["RetryCallState"], t.Union[None, t.Awaitable[None]]]] = None,
        reraise: bool = False,
        retry_error_cls: t.Type["RetryError"] = RetryError,
        retry_error_callback: t.Optional[t.Callable[["RetryCallState"], t.Union[t.Any, t.Awaitable[t.Any]]]] = None,
    ) -> None:
        super().__init__(
            sleep=sleep,  # type: ignore[arg-type]
            stop=stop,  # type: ignore[arg-type]
            wait=wait,  # type: ignore[arg-type]
            retry=retry,  # type: ignore[arg-type]
            before=before,  # type: ignore[arg-type]
            after=after,  # type: ignore[arg-type]
            before_sleep=before_sleep,  # type: ignore[arg-type]
            reraise=reraise,
            retry_error_cls=retry_error_cls,
            retry_error_callback=retry_error_callback,
        )

    async def __call__(  # type: ignore[override]
        self, fn: WrappedFn, *args: t.Any, **kwargs: t.Any
    ) -> WrappedFnReturnT:
        self.begin()

        retry_state = RetryCallState(retry_object=self, fn=fn, args=args, kwargs=kwargs)
        while True:
            do = await self.iter(retry_state=retry_state)
            if isinstance(do, DoAttempt):
                try:
                    result = await fn(*args, **kwargs)
                except BaseException:  # noqa: B902
                    retry_state.set_exception(sys.exc_info())  # type: ignore[arg-type]
                else:
                    retry_state.set_result(result)
            elif isinstance(do, DoSleep):
                retry_state.prepare_for_next_attempt()
                await self.sleep(do)  # type: ignore[misc]
            else:
                return do  # type: ignore[no-any-return]

    @classmethod
    def _wrap_action_func(cls, fn: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
        if _is_coroutine_callable(fn):
            return fn

        async def inner(*args: t.Any, **kwargs: t.Any) -> t.Any:
            return fn(*args, **kwargs)

        return inner

    async def _run_retry(self, retry_state: "RetryCallState") -> None:  # type: ignore[override]
        self.iter_state["retry_run_result"] = await self._wrap_action_func(self.retry)(retry_state)

    async def _run_wait(self, retry_state: "RetryCallState") -> None:  # type: ignore[override]
        if self.wait:
            sleep = await self._wrap_action_func(self.wait)(retry_state)
        else:
            sleep = 0.0

        retry_state.upcoming_sleep = sleep

    async def _run_stop(self, retry_state: "RetryCallState") -> None:  # type: ignore[override]
        self.statistics["delay_since_first_attempt"] = retry_state.seconds_since_start
        self.iter_state["stop_run_result"] = await self._wrap_action_func(self.stop)(retry_state)

    async def iter(self, retry_state: "RetryCallState") -> t.Union[DoAttempt, DoSleep, t.Any]:  # noqa: A003
        self.iter_state.clear()
        result = None
        for action in self._get_iter_actions(retry_state):
            result = await action(retry_state)
        return result

    def __iter__(self) -> t.Generator[AttemptManager, None, None]:
        raise TypeError("AsyncRetrying object is not iterable")

    def __aiter__(self) -> "AsyncRetrying":
        self.begin()
        self._retry_state = RetryCallState(self, fn=None, args=(), kwargs={})
        return self

    async def __anext__(self) -> AttemptManager:
        while True:
            do = await self.iter(retry_state=self._retry_state)
            if do is None:
                raise StopAsyncIteration
            elif isinstance(do, DoAttempt):
                return AttemptManager(retry_state=self._retry_state)
            elif isinstance(do, DoSleep):
                self._retry_state.prepare_for_next_attempt()
                await self.sleep(do)  # type: ignore[misc]
            else:
                raise StopAsyncIteration

    def wraps(self, fn: WrappedFn) -> WrappedFn:
        fn = super().wraps(fn)
        # Ensure wrapper is recognized as a coroutine function.

        @functools.wraps(fn, functools.WRAPPER_ASSIGNMENTS + ("__defaults__", "__kwdefaults__"))
        async def async_wrapped(*args: t.Any, **kwargs: t.Any) -> t.Any:
            return await fn(*args, **kwargs)

        # Preserve attributes
        async_wrapped.retry = fn.retry  # type: ignore[attr-defined]
        async_wrapped.retry_with = fn.retry_with  # type: ignore[attr-defined]

        return async_wrapped  # type: ignore[return-value]


__all__ = [
    "retry_all",
    "retry_always",
    "retry_any",
    "retry_if_exception",
    "retry_if_exception_type",
    "retry_if_exception_cause_type",
    "retry_if_not_exception_type",
    "retry_if_not_result",
    "retry_if_result",
    "retry_never",
    "retry_unless_exception_type",
    "retry_if_exception_message",
    "retry_if_not_exception_message",
    "stop_after_attempt",
    "stop_after_delay",
    "stop_before_delay",
    "stop_all",
    "stop_any",
    "stop_never",
    "stop_when_event_set",
    "wait_chain",
    "wait_combine",
    "wait_exponential",
    "wait_fixed",
    "wait_incrementing",
    "wait_none",
    "wait_random",
    "wait_random_exponential",
    "wait_full_jitter",
    "wait_exponential_jitter",
    "WrappedFn",
    "AsyncRetrying",
]
