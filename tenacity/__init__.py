# Copyright 2016-2018 Julien Danjou
# Copyright 2017 Elisey Zanko
# Copyright 2016 Étienne Bersac
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
import dataclasses
import functools
import sys
import threading
import time
import typing as t
import warnings
from abc import ABC, abstractmethod
from concurrent import futures

from . import _utils

# Import all built-in after strategies for easier usage.
from .after import after_log, after_nothing

# Import all built-in before strategies for easier usage.
from .before import before_log, before_nothing

# Import all built-in before sleep strategies for easier usage.
from .before_sleep import before_sleep_log, before_sleep_nothing

# Import all nap strategies for easier usage.
from .nap import sleep, sleep_using_event

# Import all built-in retry strategies for easier usage.
from .retry import (
    retry_all,
    retry_always,
    retry_any,
    retry_base,
    retry_if_exception,
    retry_if_exception_cause_type,
    retry_if_exception_message,
    retry_if_exception_type,
    retry_if_not_exception_message,
    retry_if_not_exception_type,
    retry_if_not_result,
    retry_if_result,
    retry_never,
    retry_unless_exception_type,
)

# Import all built-in stop strategies for easier usage.
from .stop import (
    stop_after_attempt,
    stop_after_delay,
    stop_all,
    stop_any,
    stop_before_delay,
    stop_never,
    stop_when_event_set,
)

# Import all built-in wait strategies for easier usage.
from .wait import (
    wait_chain,
    wait_combine,
    wait_exception,
    wait_exponential,
    wait_exponential_jitter,
    wait_fixed,
    wait_incrementing,
    wait_none,
    wait_random,
    wait_random_exponential,
)
from .wait import wait_random_exponential as wait_full_jitter

try:
    import tornado
except ImportError:
    tornado = None  # type: ignore[assignment]

if t.TYPE_CHECKING:
    if sys.version_info >= (3, 11):
        from typing import Self
    else:
        from typing_extensions import Self

    import types

    from . import asyncio as tasyncio
    from .retry import RetryBaseT
    from .stop import StopBaseT
    from .wait import WaitBaseT


WrappedFnReturnT = t.TypeVar("WrappedFnReturnT")
WrappedFn = t.TypeVar("WrappedFn", bound=t.Callable[..., t.Any])
P = t.ParamSpec("P")
R = t.TypeVar("R")


@dataclasses.dataclass(slots=True)
class IterState:
    actions: list[t.Callable[["RetryCallState"], t.Any]] = dataclasses.field(
        default_factory=list
    )
    retry_run_result: bool = False
    stop_run_result: bool = False
    is_explicit_retry: bool = False

    def reset(self) -> None:
        self.actions = []
        self.retry_run_result = False
        self.stop_run_result = False
        self.is_explicit_retry = False


class TryAgain(Exception):
    """Always retry the executed function when raised."""


NO_RESULT = object()


class DoAttempt:
    pass


class DoSleep(float):
    pass


class BaseAction:
    """Base class for representing actions to take by retry object.

    Concrete implementations must define:
    - __init__: to initialize all necessary fields
    - REPR_FIELDS: class variable specifying attributes to include in repr(self)
    - NAME: for identification in retry object methods and callbacks
    """

    REPR_FIELDS: t.Sequence[str] = ()
    NAME: str | None = None

    def __repr__(self) -> str:
        state_str = ", ".join(
            f"{field}={getattr(self, field)!r}" for field in self.REPR_FIELDS
        )
        return f"{self.__class__.__name__}({state_str})"

    def __str__(self) -> str:
        return repr(self)


class RetryAction(BaseAction):
    REPR_FIELDS = ("sleep",)
    NAME = "retry"

    def __init__(self, sleep: t.SupportsFloat) -> None:
        self.sleep = float(sleep)


_unset = object()


def _first_set(first: t.Any | object, second: t.Any) -> t.Any:
    return second if first is _unset else first


class RetryError(Exception):
    """Encapsulates the last attempt instance right before giving up."""

    def __init__(self, last_attempt: "Future") -> None:
        self.last_attempt = last_attempt
        super().__init__(last_attempt)

    def reraise(self) -> t.NoReturn:
        if self.last_attempt.failed:
            raise self.last_attempt.result()
        raise self

    def __str__(self) -> str:
        return f"{self.__class__.__name__}[{self.last_attempt}]"


class AttemptManager:
    """Manage attempt context."""

    def __init__(self, retry_state: "RetryCallState"):
        self.retry_state = retry_state

    def __enter__(self) -> None:
        pass

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: t.Optional["types.TracebackType"],
    ) -> bool | None:
        if exc_type is not None and exc_value is not None:
            self.retry_state.set_exception((exc_type, exc_value, traceback))
            return True  # Swallow exception.
        # We don't have the result, actually.
        self.retry_state.set_result(None)
        return None

    async def __aenter__(self) -> None:
        pass

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: t.Optional["types.TracebackType"],
    ) -> bool | None:
        return self.__exit__(exc_type, exc_value, traceback)


class BaseRetrying(ABC):
    def __init__(
        self,
        sleep: t.Callable[[int | float], None] = sleep,
        stop: "StopBaseT" = stop_never,
        wait: "WaitBaseT" = wait_none(),
        retry: "RetryBaseT" = retry_if_exception_type(),
        before: t.Callable[["RetryCallState"], None] = before_nothing,
        after: t.Callable[["RetryCallState"], None] = after_nothing,
        before_sleep: t.Callable[["RetryCallState"], None] | None = None,
        reraise: bool = False,
        retry_error_cls: type[RetryError] = RetryError,
        retry_error_callback: t.Callable[["RetryCallState"], t.Any] | None = None,
        name: str | None = None,
        enabled: bool = True,
    ):
        self.sleep = sleep
        self.stop = stop
        self.wait = wait
        self.retry = retry
        self.before = before
        self.after = after
        self.before_sleep = before_sleep
        self.reraise = reraise
        self._local = threading.local()
        self.retry_error_cls = retry_error_cls
        self.retry_error_callback = retry_error_callback
        self._name = name
        self.enabled = enabled

    def copy(
        self,
        sleep: t.Callable[[int | float], None] | object = _unset,
        stop: t.Union["StopBaseT", object] = _unset,
        wait: t.Union["WaitBaseT", object] = _unset,
        retry: retry_base | object = _unset,
        before: t.Callable[["RetryCallState"], None] | object = _unset,
        after: t.Callable[["RetryCallState"], None] | object = _unset,
        before_sleep: t.Callable[["RetryCallState"], None] | None | object = _unset,
        reraise: bool | object = _unset,
        retry_error_cls: type[RetryError] | object = _unset,
        retry_error_callback: t.Callable[["RetryCallState"], t.Any]
        | None
        | object = _unset,
        name: str | None | object = _unset,
        enabled: bool | object = _unset,
    ) -> "Self":
        """Copy this object with some parameters changed if needed."""
        return self.__class__(
            sleep=_first_set(sleep, self.sleep),
            stop=_first_set(stop, self.stop),
            wait=_first_set(wait, self.wait),
            retry=_first_set(retry, self.retry),
            before=_first_set(before, self.before),
            after=_first_set(after, self.after),
            before_sleep=_first_set(before_sleep, self.before_sleep),
            reraise=_first_set(reraise, self.reraise),
            retry_error_cls=_first_set(retry_error_cls, self.retry_error_cls),
            retry_error_callback=_first_set(
                retry_error_callback, self.retry_error_callback
            ),
            name=_first_set(name, self._name),
            enabled=_first_set(enabled, self.enabled),
        )

    def __str__(self) -> str:
        return self._name if self._name is not None else "<unknown>"

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} object at 0x{id(self):x} ("
            f"stop={self.stop}, "
            f"wait={self.wait}, "
            f"sleep={self.sleep}, "
            f"retry={self.retry}, "
            f"before={self.before}, "
            f"after={self.after}, "
            f"name={self._name!r})>"
        )

    @property
    def statistics(self) -> dict[str, t.Any]:
        """Return a dictionary of runtime statistics.

        This dictionary will be empty when the controller has never been
        ran. When it is running or has ran previously it should have (but
        may not) have useful and/or informational keys and values when
        running is underway and/or completed.

        .. warning:: The keys in this dictionary **should** be somewhat
                     stable (not changing), but their existence **may**
                     change between major releases as new statistics are
                     gathered or removed so before accessing keys ensure that
                     they actually exist and handle when they do not.

        .. note:: The values in this dictionary are local to the thread
                  running call (so if multiple threads share the same retrying
                  object - either directly or indirectly) they will each have
                  their own view of statistics they have collected (in the
                  future we may provide a way to aggregate the various
                  statistics from each thread).
        """
        if not hasattr(self._local, "statistics"):
            self._local.statistics = t.cast("dict[str, t.Any]", {})
        return self._local.statistics  # type: ignore[no-any-return]

    @property
    def iter_state(self) -> IterState:
        if not hasattr(self._local, "iter_state"):
            self._local.iter_state = IterState()
        return self._local.iter_state  # type: ignore[no-any-return]

    def wraps(self, f: t.Callable[P, R]) -> "_RetryDecorated[P, R]":
        """Wrap a function for retrying.

        :param f: A function to wrap for retrying.
        """

        @functools.wraps(
            f, functools.WRAPPER_ASSIGNMENTS + ("__defaults__", "__kwdefaults__")
        )
        def wrapped_f(*args: t.Any, **kw: t.Any) -> t.Any:
            if not self.enabled:
                return f(*args, **kw)
            # Always create a copy to prevent overwriting the local contexts when
            # calling the same wrapped functions multiple times in the same stack
            copy = self.copy()
            wrapped_f.statistics = copy.statistics  # type: ignore[attr-defined]
            return copy(f, *args, **kw)

        @functools.wraps(
            f, functools.WRAPPER_ASSIGNMENTS + ("__defaults__", "__kwdefaults__")
        )
        def wrapped_gen_f(
            *args: t.Any, **kw: t.Any
        ) -> t.Generator[t.Any, t.Any, t.Any]:
            if not self.enabled:
                yield from f(*args, **kw)
                return
            copy = self.copy()
            wrapped_gen_f.statistics = copy.statistics  # type: ignore[attr-defined]
            copy.begin()
            retry_state = RetryCallState(retry_object=copy, fn=f, args=args, kwargs=kw)
            while True:
                do = copy.iter(retry_state=retry_state)
                if isinstance(do, DoAttempt):
                    try:
                        result = yield from f(*args, **kw)
                    except GeneratorExit:
                        raise
                    except BaseException:
                        retry_state.set_exception(sys.exc_info())  # type: ignore[arg-type]
                    else:
                        retry_state.set_result(result)
                elif isinstance(do, DoSleep):
                    retry_state.prepare_for_next_attempt()
                    copy.sleep(do)
                else:
                    return do

        result_f = wrapped_gen_f if _utils.is_generator_callable(f) else wrapped_f

        def retry_with(*args: t.Any, **kwargs: t.Any) -> "_RetryDecorated[P, R]":
            return self.copy(*args, **kwargs).wraps(f)

        # Preserve attributes
        result_f.retry = self  # type: ignore[attr-defined]
        result_f.retry_with = retry_with  # type: ignore[attr-defined]
        result_f.statistics = {}  # type: ignore[attr-defined]

        return t.cast("_RetryDecorated[P, R]", result_f)

    def begin(self) -> None:
        self.statistics.clear()
        self.statistics["start_time"] = time.monotonic()
        self.statistics["attempt_number"] = 1
        self.statistics["idle_for"] = 0
        self.statistics["delay_since_first_attempt"] = 0

    def _add_action_func(self, fn: t.Callable[..., t.Any]) -> None:
        self.iter_state.actions.append(fn)

    def _run_retry(self, retry_state: "RetryCallState") -> None:
        self.iter_state.retry_run_result = self.retry(retry_state)

    def _run_wait(self, retry_state: "RetryCallState") -> None:
        if self.wait:
            sleep = self.wait(retry_state)
        else:
            sleep = 0.0

        retry_state.upcoming_sleep = sleep

    def _run_stop(self, retry_state: "RetryCallState") -> None:
        self.statistics["delay_since_first_attempt"] = retry_state.seconds_since_start
        self.iter_state.stop_run_result = self.stop(retry_state)

    def iter(self, retry_state: "RetryCallState") -> DoAttempt | DoSleep | t.Any:
        self._begin_iter(retry_state)
        result = None
        for action in self.iter_state.actions:
            result = action(retry_state)
        return result

    def _begin_iter(self, retry_state: "RetryCallState") -> None:
        self.iter_state.reset()

        fut = retry_state.outcome
        if fut is None:
            if self.before is not None:
                self._add_action_func(self.before)
            self._add_action_func(lambda rs: DoAttempt())
            return

        self.iter_state.is_explicit_retry = fut.failed and isinstance(
            fut.exception(), TryAgain
        )
        if not self.iter_state.is_explicit_retry:
            self._add_action_func(self._run_retry)
        self._add_action_func(self._post_retry_check_actions)

    def _post_retry_check_actions(self, retry_state: "RetryCallState") -> None:
        if not (self.iter_state.is_explicit_retry or self.iter_state.retry_run_result):
            self._add_action_func(lambda rs: rs.outcome.result())
            return

        if self.after is not None:
            self._add_action_func(self.after)

        self._add_action_func(self._run_wait)
        self._add_action_func(self._run_stop)
        self._add_action_func(self._post_stop_check_actions)

    def _post_stop_check_actions(self, retry_state: "RetryCallState") -> None:
        if self.iter_state.stop_run_result:
            if self.retry_error_callback:
                self._add_action_func(self.retry_error_callback)
                return

            def exc_check(rs: "RetryCallState") -> None:
                fut = t.cast("Future", rs.outcome)
                retry_exc = self.retry_error_cls(fut)
                if self.reraise:
                    retry_exc.reraise()
                raise retry_exc from fut.exception()

            self._add_action_func(exc_check)
            return

        def next_action(rs: "RetryCallState") -> None:
            sleep = rs.upcoming_sleep
            rs.next_action = RetryAction(sleep)
            rs.idle_for += sleep
            self.statistics["idle_for"] += sleep
            self.statistics["attempt_number"] += 1

        self._add_action_func(next_action)

        if self.before_sleep is not None:
            self._add_action_func(self.before_sleep)

        self._add_action_func(lambda rs: DoSleep(rs.upcoming_sleep))

    def __iter__(self) -> t.Generator[AttemptManager, None, None]:
        self.begin()

        retry_state = RetryCallState(self, fn=None, args=(), kwargs={})
        while True:
            do = self.iter(retry_state=retry_state)
            if isinstance(do, DoAttempt):
                yield AttemptManager(retry_state=retry_state)
            elif isinstance(do, DoSleep):
                retry_state.prepare_for_next_attempt()
                self.sleep(do)
            else:
                break

    @abstractmethod
    def __call__(
        self,
        fn: t.Callable[..., WrappedFnReturnT],
        *args: t.Any,
        **kwargs: t.Any,
    ) -> WrappedFnReturnT:
        pass


class Retrying(BaseRetrying):
    """Retrying controller."""

    def __call__(
        self,
        fn: t.Callable[..., WrappedFnReturnT],
        *args: t.Any,
        **kwargs: t.Any,
    ) -> WrappedFnReturnT:
        self.begin()

        retry_state = RetryCallState(retry_object=self, fn=fn, args=args, kwargs=kwargs)
        while True:
            do = self.iter(retry_state=retry_state)
            if isinstance(do, DoAttempt):
                try:
                    result = fn(*args, **kwargs)
                except BaseException:
                    retry_state.set_exception(sys.exc_info())  # type: ignore[arg-type]
                else:
                    retry_state.set_result(result)
            elif isinstance(do, DoSleep):
                retry_state.prepare_for_next_attempt()
                self.sleep(do)
            else:
                return do  # type: ignore[no-any-return]


class Future(futures.Future[t.Any]):
    """Encapsulates a (future or past) attempted call to a target function."""

    def __init__(self, attempt_number: int) -> None:
        super().__init__()
        self.attempt_number = attempt_number

    @property
    def failed(self) -> bool:
        """Return whether a exception is being held in this future."""
        return self.exception() is not None

    @classmethod
    def construct(
        cls, attempt_number: int, value: t.Any, has_exception: bool
    ) -> "Future":
        """Construct a new Future object."""
        fut = cls(attempt_number)
        if has_exception:
            fut.set_exception(value)
        else:
            fut.set_result(value)
        return fut


class RetryCallState:
    """State related to a single call wrapped with Retrying."""

    def __init__(
        self,
        retry_object: BaseRetrying,
        fn: WrappedFn | None,
        args: t.Any,
        kwargs: t.Any,
    ) -> None:
        #: Retry call start timestamp
        self.start_time = time.monotonic()
        #: Retry manager object
        self.retry_object = retry_object
        #: Function wrapped by this retry call
        self.fn = fn
        #: Arguments of the function wrapped by this retry call
        self.args = args
        #: Keyword arguments of the function wrapped by this retry call
        self.kwargs = kwargs

        #: The number of the current attempt
        self.attempt_number: int = 1
        #: Last outcome (result or exception) produced by the function
        self.outcome: Future | None = None
        #: Timestamp of the last outcome
        self.outcome_timestamp: float | None = None
        #: Time spent sleeping in retries
        self.idle_for: float = 0.0
        #: Next action as decided by the retry manager
        self.next_action: RetryAction | None = None
        #: Next sleep time as decided by the retry manager.
        self.upcoming_sleep: float = 0.0

    def get_fn_name(self) -> str:
        """Get the name of the function being retried.

        Returns the fully-qualified name of the wrapped function when used as a
        decorator, the ``name`` passed to the retrying object when used as a
        context manager, or ``"<unknown>"`` if neither is available.
        """
        if self.fn is not None:
            return _utils.get_callback_name(self.fn)
        return str(self.retry_object)

    @property
    def seconds_since_start(self) -> float | None:
        if self.outcome_timestamp is None:
            return None
        return self.outcome_timestamp - self.start_time

    def prepare_for_next_attempt(self) -> None:
        self.outcome = None
        self.outcome_timestamp = None
        self.attempt_number += 1
        self.next_action = None

    def set_result(self, val: t.Any) -> None:
        ts = time.monotonic()
        fut = Future(self.attempt_number)
        fut.set_result(val)
        self.outcome, self.outcome_timestamp = fut, ts

    def set_exception(
        self,
        exc_info: tuple[
            type[BaseException], BaseException, "types.TracebackType| None"
        ],
    ) -> None:
        ts = time.monotonic()
        fut = Future(self.attempt_number)
        fut.set_exception(exc_info[1])
        self.outcome, self.outcome_timestamp = fut, ts

    def __repr__(self) -> str:
        if self.outcome is None:
            result = "none yet"
        elif self.outcome.failed:
            exception = self.outcome.exception()
            result = f"failed ({exception.__class__.__name__} {exception})"
        else:
            result = f"returned {self.outcome.result()}"

        slept = float(round(self.idle_for, 2))
        clsname = self.__class__.__name__
        return f"<{clsname} {id(self)}: attempt #{self.attempt_number}; slept for {slept}; last result: {result}>"


class _RetryDecorated(t.Protocol[P, R]):
    """Protocol for functions decorated with @retry.

    Provides the original callable signature plus retry control attributes.
    """

    retry: "BaseRetrying"
    statistics: dict[str, t.Any]

    def retry_with(self, *args: t.Any, **kwargs: t.Any) -> "_RetryDecorated[P, R]": ...

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...


class _AsyncRetryDecorator(t.Protocol):
    @t.overload
    def __call__(
        self, fn: "t.Callable[P, types.CoroutineType[t.Any, t.Any, R]]"
    ) -> "_RetryDecorated[P, types.CoroutineType[t.Any, t.Any, R]]": ...
    @t.overload
    def __call__(
        self, fn: t.Callable[P, t.Coroutine[t.Any, t.Any, R]]
    ) -> "_RetryDecorated[P, t.Coroutine[t.Any, t.Any, R]]": ...
    @t.overload
    def __call__(
        self, fn: t.Callable[P, t.Awaitable[R]]
    ) -> "_RetryDecorated[P, t.Awaitable[R]]": ...
    @t.overload
    def __call__(
        self, fn: t.Callable[P, R]
    ) -> "_RetryDecorated[P, t.Awaitable[R]]": ...


@t.overload
def retry(func: t.Callable[P, R]) -> _RetryDecorated[P, R]: ...


@t.overload
def retry(
    *,
    sleep: t.Callable[[int | float], t.Awaitable[None]],
    stop: "StopBaseT" = ...,
    wait: "WaitBaseT" = ...,
    retry: "RetryBaseT | tasyncio.retry.RetryBaseT" = ...,
    before: t.Callable[["RetryCallState"], None | t.Awaitable[None]] = ...,
    after: t.Callable[["RetryCallState"], None | t.Awaitable[None]] = ...,
    before_sleep: t.Callable[["RetryCallState"], None | t.Awaitable[None]] | None = ...,
    reraise: bool = ...,
    retry_error_cls: type["RetryError"] = ...,
    retry_error_callback: t.Callable[["RetryCallState"], t.Any | t.Awaitable[t.Any]]
    | None = ...,
    enabled: bool = ...,
) -> _AsyncRetryDecorator: ...


@t.overload
def retry(
    sleep: t.Callable[[int | float], None] = sleep,
    stop: "StopBaseT" = stop_never,
    wait: "WaitBaseT" = wait_none(),
    retry: "RetryBaseT | tasyncio.retry.RetryBaseT" = retry_if_exception_type(),
    before: t.Callable[["RetryCallState"], None | t.Awaitable[None]] = before_nothing,
    after: t.Callable[["RetryCallState"], None | t.Awaitable[None]] = after_nothing,
    before_sleep: t.Callable[["RetryCallState"], None | t.Awaitable[None]]
    | None = None,
    reraise: bool = False,
    retry_error_cls: type["RetryError"] = RetryError,
    retry_error_callback: t.Callable[["RetryCallState"], t.Any | t.Awaitable[t.Any]]
    | None = None,
    enabled: bool = True,
) -> t.Callable[[t.Callable[P, R]], _RetryDecorated[P, R]]: ...


def retry(*dargs: t.Any, **dkw: t.Any) -> t.Any:
    """Wrap a function with a new `Retrying` object.

    :param dargs: positional arguments passed to Retrying object
    :param dkw: keyword arguments passed to the Retrying object
    """
    # support both @retry and @retry() as valid syntax
    if len(dargs) == 1 and callable(dargs[0]):
        return retry()(dargs[0])

    def wrap(f: t.Callable[P, R]) -> _RetryDecorated[P, R]:
        if isinstance(f, retry_base):
            warnings.warn(
                f"Got retry_base instance ({f.__class__.__name__}) as callable argument, "
                f"this will probably hang indefinitely (did you mean retry={f.__class__.__name__}(...)?)",
                stacklevel=2,
            )
        r: BaseRetrying
        sleep = dkw.get("sleep")
        if (
            _utils.is_coroutine_callable(f)
            or _utils.is_async_gen_callable(f)
            or (sleep is not None and _utils.is_coroutine_callable(sleep))
        ):
            r = AsyncRetrying(*dargs, **dkw)
        elif (
            tornado
            and hasattr(tornado.gen, "is_coroutine_function")
            and tornado.gen.is_coroutine_function(f)
        ):
            r = TornadoRetrying(*dargs, **dkw)
        else:
            r = Retrying(*dargs, **dkw)

        return r.wraps(f)

    return wrap


from tenacity.asyncio import AsyncRetrying  # noqa: E402

if tornado:
    from tenacity.tornadoweb import TornadoRetrying


__all__ = [
    "NO_RESULT",
    "AsyncRetrying",
    "AttemptManager",
    "BaseAction",
    "BaseRetrying",
    "DoAttempt",
    "DoSleep",
    "Future",
    "RetryAction",
    "RetryCallState",
    "RetryError",
    "Retrying",
    "TryAgain",
    "WrappedFn",
    "after_log",
    "after_nothing",
    "before_log",
    "before_nothing",
    "before_sleep_log",
    "before_sleep_nothing",
    "retry",
    "retry_all",
    "retry_always",
    "retry_any",
    "retry_base",
    "retry_if_exception",
    "retry_if_exception_cause_type",
    "retry_if_exception_message",
    "retry_if_exception_type",
    "retry_if_not_exception_message",
    "retry_if_not_exception_type",
    "retry_if_not_result",
    "retry_if_result",
    "retry_never",
    "retry_unless_exception_type",
    "sleep",
    "sleep_using_event",
    "stop_after_attempt",
    "stop_after_delay",
    "stop_all",
    "stop_any",
    "stop_before_delay",
    "stop_never",
    "stop_when_event_set",
    "wait_chain",
    "wait_combine",
    "wait_exception",
    "wait_exponential",
    "wait_exponential_jitter",
    "wait_fixed",
    "wait_full_jitter",
    "wait_incrementing",
    "wait_none",
    "wait_random",
    "wait_random_exponential",
]
