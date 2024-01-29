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

from tenacity import retry_base

if typing.TYPE_CHECKING:
    from tenacity import RetryCallState


class retry_base(retry_base):  # type: ignore[no-redef]
    """Abstract base class for retry strategies."""

    @abc.abstractmethod
    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        pass


RetryBaseT = typing.Union[retry_base, typing.Callable[["RetryCallState"], typing.Awaitable[bool]]]


class _retry_never(retry_base):
    """Retry strategy that never rejects any result."""

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        return False


retry_never = _retry_never()


class _retry_always(retry_base):
    """Retry strategy that always rejects any result."""

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        return True


retry_always = _retry_always()


class retry_if_exception(retry_base):
    """Retry strategy that retries if an exception verifies a predicate."""

    def __init__(self, predicate: typing.Callable[[BaseException], typing.Awaitable[bool]]) -> None:
        self.predicate = predicate

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        if retry_state.outcome is None:
            raise RuntimeError("__call__() called before outcome was set")

        if retry_state.outcome.failed:
            exception = retry_state.outcome.exception()
            if exception is None:
                raise RuntimeError("outcome failed but the exception is None")
            return await self.predicate(exception)
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

        async def predicate(e: BaseException) -> bool:
            return isinstance(e, exception_types)

        super().__init__(predicate)


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

        async def predicate(e: BaseException) -> bool:
            return not isinstance(e, exception_types)

        super().__init__(predicate)


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

        async def predicate(e: BaseException) -> bool:
            return not isinstance(e, exception_types)

        super().__init__(predicate)

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        if retry_state.outcome is None:
            raise RuntimeError("__call__() called before outcome was set")

        # always retry if no exception was raised
        if not retry_state.outcome.failed:
            return True

        exception = retry_state.outcome.exception()
        if exception is None:
            raise RuntimeError("outcome failed but the exception is None")
        return await self.predicate(exception)


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

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
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

    def __init__(self, predicate: typing.Callable[[typing.Any], typing.Awaitable[bool]]) -> None:
        self.predicate = predicate

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        if retry_state.outcome is None:
            raise RuntimeError("__call__() called before outcome was set")

        if not retry_state.outcome.failed:
            return await self.predicate(retry_state.outcome.result())
        else:
            return False


class retry_if_not_result(retry_base):
    """Retries if the result refutes a predicate."""

    def __init__(self, predicate: typing.Callable[[typing.Any], typing.Awaitable[bool]]) -> None:
        self.predicate = predicate

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        if retry_state.outcome is None:
            raise RuntimeError("__call__() called before outcome was set")

        if not retry_state.outcome.failed:
            return not await self.predicate(retry_state.outcome.result())
        else:
            return False


class retry_if_exception_message(retry_if_exception):
    """Retries if an exception message equals or matches."""

    def __init__(
        self,
        message: typing.Optional[str] = None,
        match: typing.Optional[str] = None,
    ) -> None:
        if message and match:
            raise TypeError(f"{self.__class__.__name__}() takes either 'message' or 'match', not both")

        # set predicate
        if message:

            async def message_fnc(exception: BaseException) -> bool:
                return message == str(exception)

            predicate = message_fnc
        elif match:
            prog = re.compile(match)

            async def match_fnc(exception: BaseException) -> bool:
                return bool(prog.match(str(exception)))

            predicate = match_fnc
        else:
            raise TypeError(f"{self.__class__.__name__}() missing 1 required argument 'message' or 'match'")

        super().__init__(predicate)


class retry_if_not_exception_message(retry_if_exception_message):
    """Retries until an exception message equals or matches."""

    def __init__(
        self,
        message: typing.Optional[str] = None,
        match: typing.Optional[str] = None,
    ) -> None:
        super().__init__(message, match)
        if_predicate = self.predicate

        # invert predicate
        async def predicate(e: BaseException) -> bool:
            return not if_predicate(e)

        self.predicate = predicate

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        if retry_state.outcome is None:
            raise RuntimeError("__call__() called before outcome was set")

        if not retry_state.outcome.failed:
            return True

        exception = retry_state.outcome.exception()
        if exception is None:
            raise RuntimeError("outcome failed but the exception is None")
        return await self.predicate(exception)


class retry_any(retry_base):
    """Retries if any of the retries condition is valid."""

    def __init__(self, *retries: retry_base) -> None:
        self.retries = retries

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        return any(r(retry_state) for r in self.retries)


class retry_all(retry_base):
    """Retries if all the retries condition are valid."""

    def __init__(self, *retries: retry_base) -> None:
        self.retries = retries

    async def __call__(self, retry_state: "RetryCallState") -> bool:  # type: ignore[override]
        return all(r(retry_state) for r in self.retries)
