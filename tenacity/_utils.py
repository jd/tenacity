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
import contextlib
import functools
import inspect
import sys
import typing
from datetime import timedelta

# sys.maxsize:
# An integer giving the maximum value a variable of type Py_ssize_t can take.
MAX_WAIT = sys.maxsize / 2


class LoggerProtocol(typing.Protocol):
    """
    Protocol used by utils expecting a logger (eg: before_log).

    Compatible with logging, structlog, loguru, etc...
    """

    def log(
        self, level: int, msg: str, /, *args: typing.Any, **kwargs: typing.Any
    ) -> typing.Any: ...


def find_ordinal(pos_num: int) -> str:
    # See: https://en.wikipedia.org/wiki/English_numerals#Ordinal_numbers

    if 11 <= (pos_num % 100) <= 13:
        return "th"

    if pos_num == 0:
        return "th"
    if pos_num == 1:
        return "st"
    if pos_num == 2:
        return "nd"
    if pos_num == 3:
        return "rd"
    if 4 <= pos_num <= 20:
        return "th"
    return find_ordinal(pos_num % 10)


def to_ordinal(pos_num: int) -> str:
    return f"{pos_num}{find_ordinal(pos_num)}"


def get_callback_name(cb: typing.Callable[..., typing.Any]) -> str:
    """Get a callback fully-qualified name.

    If no name can be produced ``repr(cb)`` is called and returned.
    """
    segments = []
    try:
        segments.append(cb.__qualname__)
    except AttributeError:
        with contextlib.suppress(AttributeError):
            segments.append(cb.__name__)
    if not segments:
        return repr(cb)
    with contextlib.suppress(AttributeError):
        # When running under sphinx it appears this can be none?
        if cb.__module__:
            segments.insert(0, cb.__module__)
    return ".".join(segments)


time_unit_type = int | float | timedelta


def to_seconds(time_unit: time_unit_type) -> float:
    return float(
        time_unit.total_seconds() if isinstance(time_unit, timedelta) else time_unit
    )


def is_coroutine_callable(call: typing.Callable[..., typing.Any]) -> bool:
    if inspect.isclass(call):
        return False
    if inspect.iscoroutinefunction(call):
        return True
    partial_call = isinstance(call, functools.partial) and call.func
    dunder_call = partial_call or getattr(call, "__call__", None)  # noqa: B004
    return inspect.iscoroutinefunction(dunder_call)


def wrap_to_async_func(
    call: typing.Callable[..., typing.Any],
) -> typing.Callable[..., typing.Awaitable[typing.Any]]:
    if is_coroutine_callable(call):
        return call

    async def inner(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        return call(*args, **kwargs)

    return inner
