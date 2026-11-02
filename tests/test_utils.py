import contextlib
import functools
import inspect
import logging

import tenacity
from tenacity import _utils


def test_is_coroutine_callable() -> None:
    async def async_func() -> None:
        pass

    def sync_func() -> None:
        pass

    class AsyncClass:
        async def __call__(self) -> None:
            pass

    class SyncClass:
        def __call__(self) -> None:
            pass

    lambda_fn = lambda: None  # noqa: E731

    partial_async_func = functools.partial(async_func)
    partial_sync_func = functools.partial(sync_func)
    partial_async_class = functools.partial(AsyncClass().__call__)
    partial_sync_class = functools.partial(SyncClass().__call__)
    partial_lambda_fn = functools.partial(lambda_fn)

    assert _utils.is_coroutine_callable(async_func) is True
    assert _utils.is_coroutine_callable(sync_func) is False
    assert _utils.is_coroutine_callable(AsyncClass) is False
    assert _utils.is_coroutine_callable(AsyncClass()) is True
    assert _utils.is_coroutine_callable(SyncClass) is False
    assert _utils.is_coroutine_callable(SyncClass()) is False
    assert _utils.is_coroutine_callable(lambda_fn) is False

    assert _utils.is_coroutine_callable(partial_async_func) is True
    assert _utils.is_coroutine_callable(partial_sync_func) is False
    assert _utils.is_coroutine_callable(partial_async_class) is True
    assert _utils.is_coroutine_callable(partial_sync_class) is False
    assert _utils.is_coroutine_callable(partial_lambda_fn) is False


def test_logger_protocol_log_is_positional_only() -> None:
    # Regression test for #771: loguru's `log` stub declares its
    # parameters positional-only, so LoggerProtocol must not promise
    # keyword calls (eg: `logger.log(level=..., msg=...)`) or a type
    # checker rejects loguru loggers as LoggerProtocol.
    params = inspect.signature(_utils.LoggerProtocol.log).parameters
    assert params["level"].kind is inspect.Parameter.POSITIONAL_ONLY
    assert params["msg"].kind is inspect.Parameter.POSITIONAL_ONLY


def test_before_sleep_log_with_positional_only_logger() -> None:
    # Mirrors loguru's positional-only `log` shape at runtime: a
    # logger that can only be called positionally must still work
    # with before_sleep_log, as must a stdlib logger.
    messages: list[str] = []

    class PositionalOnlyLogger:
        def log(self, level: int, msg: str, /) -> None:
            messages.append(msg)

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(2),
        wait=tenacity.wait_fixed(0),
        before_sleep=tenacity.before_sleep_log(PositionalOnlyLogger(), logging.INFO),
        reraise=True,
    )
    def flaky() -> None:
        raise ValueError("boom")

    with contextlib.suppress(ValueError):
        flaky()
    assert len(messages) == 1
    assert "flaky" in messages[0]


def test_find_ordinal() -> None:
    assert _utils.find_ordinal(1) == "st"
    assert _utils.find_ordinal(2) == "nd"
    assert _utils.find_ordinal(3) == "rd"
    assert _utils.find_ordinal(4) == "th"
    assert _utils.find_ordinal(11) == "th"
    assert _utils.find_ordinal(12) == "th"
    assert _utils.find_ordinal(13) == "th"
    assert _utils.find_ordinal(21) == "st"
    assert _utils.find_ordinal(22) == "nd"
    assert _utils.find_ordinal(23) == "rd"
    assert _utils.find_ordinal(111) == "th"
    assert _utils.find_ordinal(112) == "th"
    assert _utils.find_ordinal(113) == "th"
