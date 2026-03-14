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
import functools
import inspect
import logging
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
    if pos_num == 0:
        return "th"
    elif pos_num == 1:
        return "st"
    elif pos_num == 2:
        return "nd"
    elif pos_num == 3:
        return "rd"
    elif 4 <= pos_num <= 20:
        return "th"
    else:
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
        try:
            segments.append(cb.__name__)
        except AttributeError:
            pass
    if not segments:
        return repr(cb)
    else:
        try:
            # When running under sphinx it appears this can be none?
            if cb.__module__:
                segments.insert(0, cb.__module__)
        except AttributeError:
            pass
        return ".".join(segments)


def format_log_value(value: typing.Any) -> str:
    """Format values for single-line log messages."""
    return str(value).replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\r")


def resolve_retry_label(
    retry_object: typing.Any,
    fn: typing.Optional[typing.Callable[..., typing.Any]],
    label: typing.Optional[str],
    fallback: str = "<unknown>",
) -> str:
    if label is not None:
        return label
    if fn is not None:
        return get_callback_name(fn)
    if retry_object is None:
        return fallback

    retry_type = retry_object.__class__
    return f"{retry_type.__module__}.{retry_type.__qualname__} block 0x{id(retry_object):x}"


def get_retry_label(
    retry_state: typing.Any, fallback: str = "<unknown>"
) -> str:
    retry_label = getattr(retry_state, "retry_label", None)
    if retry_label is not None:
        return retry_label

    retry_object = getattr(retry_state, "retry_object", None)
    label = getattr(retry_object, "label", None)
    fn = getattr(retry_state, "fn", None)
    return resolve_retry_label(retry_object, fn, label, fallback)


def get_callback_target_name(
    retry_state: typing.Any, fallback: str = "<unknown>"
) -> str:
    """Resolve a logging target name from label/callable context."""
    return format_log_value(get_retry_label(retry_state, fallback=fallback))


def log_with_retry_label(
    logger: LoggerProtocol,
    log_level: int,
    message: str,
    retry_state: typing.Any,
    **kwargs: typing.Any,
) -> typing.Any:
    extra = dict(kwargs.pop("extra", {}))
    extra["retry_label"] = get_retry_label(retry_state)
    if isinstance(logger, (logging.Logger, logging.LoggerAdapter)):
        return logger.log(log_level, message, extra=extra, **kwargs)
    return logger.log(log_level, message, **kwargs)


time_unit_type = typing.Union[int, float, timedelta]


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
    dunder_call = partial_call or getattr(call, "__call__", None)
    return inspect.iscoroutinefunction(dunder_call)


def wrap_to_async_func(
    call: typing.Callable[..., typing.Any],
) -> typing.Callable[..., typing.Awaitable[typing.Any]]:
    if is_coroutine_callable(call):
        return call

    async def inner(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        return call(*args, **kwargs)

    return inner
