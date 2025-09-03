# Copyright 2016–2021 Julien Danjou
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

import abc
import re
import typing

from . import _utils

try:
    import tornado
except ImportError:
    tornado = None

if typing.TYPE_CHECKING:
    from tenacity import RetryCallState


class retry_base(abc.ABC):
    """Abstract base class for retry strategies."""

    @abc.abstractmethod
    def __call__(self, retry_state: "RetryCallState") -> bool:
        pass

    def __and__(self, other: "retry_base") -> "retry_all":
        if isinstance(other, retry_base):
            # Delegate to the other object to allow for specific
            # implementations, such as asyncio
            return other.__rand__(self)
        return retry_all(other, self)

    def __rand__(self, other: "retry_base") -> "retry_all":
        # This is automatically invoked for inheriting classes,
        # so it helps to keep the abstraction and delegate specific
        # implementations, such as asyncio
        return retry_all(other, self)

    def __or__(self, other: "retry_base") -> "retry_any":
        if isinstance(other, retry_base):
            # Delegate to the other object to allow for specific
            # implementations, such as asyncio
            return other.__ror__(self)
        return retry_any(other, self)

    def __ror__(self, other: "retry_base") -> "retry_any":
        # This is automatically invoked for inheriting classes,
        # so it helps to keep the abstraction and delegate specific
        # implementations, such as asyncio
        return retry_any(other, self)


RetryBaseT = typing.Union[retry_base, typing.Callable[["RetryCallState"], bool]]


class _retry_never(retry_base):
    """Retry strategy that never rejects any result."""

    def __call__(self, retry_state: "RetryCallState") -> bool:
        return False


retry_never = _retry_never()


class _retry_always(retry_base):
    """Retry strategy that always rejects any result."""

    def __call__(self, retry_state: "RetryCallState") -> bool:
        return True


retry_always = _retry_always()


class retry_if_exception(retry_base):
    """Retry strategy that retries if an exception verifies a predicate."""

    def __init__(self, predicate: typing.Callable[[BaseException], bool]) -> None:
        self.predicate = predicate

    def __call__(self, retry_state: "RetryCallState") -> bool:
        if retry_state.outcome is None:
            raise RuntimeError("__call__() called before outcome was set")

        if retry_state.outcome.failed:
            exception = retry_state.outcome.exception()
            if exception is None:
                raise RuntimeError("outcome failed but the exception is None")
            return self.predicate(exception)
        else:
            return False


class retry_if_exception_type(retry_if_exception):
    """Retries if an exception has been raised of one or more types."""

    def __init__(
        self,
        exception_types: typing.Union[
            typing.Type[BaseException],
            typing.Tuple[typing.Type[BaseException], ...],
        ] = Exception,
    ) -> None:
        self.exception_types = exception_types
        super().__init__(lambda e: isinstance(e, exception_types))


class retry_if_not_exception_type(retry_if_exception):
    """Retries except an exception has been raised of one or more types."""

    def __init__(
        self,
        exception_types: typing.Union[
            typing.Type[BaseException],
            typing.Tuple[typing.Type[BaseException], ...],
        ] = Exception,
    ) -> None:
        self.exception_types = exception_types
        super().__init__(lambda e: not isinstance(e, exception_types))


class retry_unless_exception_type(retry_if_exception):
    """Retries until an exception is raised of one or more types."""

    def __init__(
        self,
        exception_types: typing.Union[
            typing.Type[BaseException],
            typing.Tuple[typing.Type[BaseException], ...],
        ] = Exception,
    ) -> None:
        self.exception_types = exception_types
        super().__init__(lambda e: not isinstance(e, exception_types))

    def __call__(self, retry_state: "RetryCallState") -> bool:
        if retry_state.outcome is None:
            raise RuntimeError("__call__() called before outcome was set")

        # always retry if no exception was raised
        if not retry_state.outcome.failed:
            return True

        exception = retry_state.outcome.exception()
        if exception is None:
            raise RuntimeError("outcome failed but the exception is None")
        return self.predicate(exception)


class retry_if_exception_cause_type(retry_base):
    """Retries if any of the causes of the raised exception is of one or more types.

    The check on the type of the cause of the exception is done recursively (until finding
    an exception in the chain that has no `__cause__`)
    """

    def __init__(
        self,
        exception_types: typing.Union[
            typing.Type[BaseException],
            typing.Tuple[typing.Type[BaseException], ...],
        ] = Exception,
    ) -> None:
        self.exception_cause_types = exception_types

    def __call__(self, retry_state: "RetryCallState") -> bool:
        if retry_state.outcome is None:
            raise RuntimeError("__call__ called before outcome was set")

        if retry_state.outcome.failed:
            exc = retry_state.outcome.exception()
            while exc is not None:
                if isinstance(exc.__cause__, self.exception_cause_types):
                    return True
                exc = exc.__cause__

        return False


class retry_if_result(retry_base):
    """Retries if the result verifies a predicate."""

    def __init__(self, predicate: typing.Callable[[typing.Any], bool]) -> None:
        self.predicate = predicate

    def __call__(self, retry_state: "RetryCallState") -> bool:
        if retry_state.outcome is None:
            raise RuntimeError("__call__() called before outcome was set")

        if not retry_state.outcome.failed:
            return self.predicate(retry_state.outcome.result())
        else:
            return False


class retry_if_not_result(retry_base):
    """Retries if the result refutes a predicate."""

    def __init__(self, predicate: typing.Callable[[typing.Any], bool]) -> None:
        self.predicate = predicate

    def __call__(self, retry_state: "RetryCallState") -> bool:
        if retry_state.outcome is None:
            raise RuntimeError("__call__() called before outcome was set")

        if not retry_state.outcome.failed:
            return not self.predicate(retry_state.outcome.result())
        else:
            return False


class retry_if_exception_message(retry_if_exception):
    """Retries if an exception message equals or matches."""

    def __init__(
        self,
        message: typing.Optional[str] = None,
        match: typing.Union[None, str, typing.Pattern[str]] = None,
    ) -> None:
        if message and match:
            raise TypeError(
                f"{self.__class__.__name__}() takes either 'message' or 'match', not both"
            )

        # set predicate
        if message:

            def message_fnc(exception: BaseException) -> bool:
                return message == str(exception)

            predicate = message_fnc
        elif match:
            prog = re.compile(match)

            def match_fnc(exception: BaseException) -> bool:
                return bool(prog.match(str(exception)))

            predicate = match_fnc
        else:
            raise TypeError(
                f"{self.__class__.__name__}() missing 1 required argument 'message' or 'match'"
            )

        super().__init__(predicate)


class retry_if_not_exception_message(retry_if_exception_message):
    """Retries until an exception message equals or matches."""

    def __init__(
        self,
        message: typing.Optional[str] = None,
        match: typing.Union[None, str, typing.Pattern[str]] = None,
    ) -> None:
        super().__init__(message, match)
        # invert predicate
        if_predicate = self.predicate
        self.predicate = lambda *args_, **kwargs_: not if_predicate(*args_, **kwargs_)

    def __call__(self, retry_state: "RetryCallState") -> bool:
        if retry_state.outcome is None:
            raise RuntimeError("__call__() called before outcome was set")

        if not retry_state.outcome.failed:
            return True

        exception = retry_state.outcome.exception()
        if exception is None:
            raise RuntimeError("outcome failed but the exception is None")
        return self.predicate(exception)


class retry_any(retry_base):
    """Retries if any of the retries condition is valid."""

    def __init__(self, *retries: retry_base) -> None:
        self.retries = retries

    def __call__(self, retry_state: "RetryCallState") -> bool:
        result = False
        for r in self.retries:
            if _utils.is_coroutine_callable(r) or (
                tornado
                and hasattr(tornado.gen, "is_coroutine_function")
                and tornado.gen.is_coroutine_function(r)
            ):
                raise TypeError(
                    "Cannot use async functions in a sync context. Make sure "
                    "you use the correct retrying object and the corresponding "
                    "async strategies"
                )
            result = result or r(retry_state)
            if result:
                break
        return result


class retry_all(retry_base):
    """Retries if all the retries condition are valid."""

    def __init__(self, *retries: retry_base) -> None:
        self.retries = retries

    def __call__(self, retry_state: "RetryCallState") -> bool:
        result = True
        for r in self.retries:
            if _utils.is_coroutine_callable(r) or (
                tornado
                and hasattr(tornado.gen, "is_coroutine_function")
                and tornado.gen.is_coroutine_function(r)
            ):
                raise TypeError(
                    "Cannot use async functions in a sync context. Make sure "
                    "you use the correct retrying object and the corresponding "
                    "async strategies"
                )
            result = result and r(retry_state)
            if not result:
                break
        return result
