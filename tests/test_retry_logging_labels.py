import asyncio
import logging
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import pytest

import tenacity
from tenacity import AsyncRetrying
from tenacity import Retrying
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import retry_if_result
from tenacity import stop_after_attempt
from tenacity import wait_fixed

try:
    from tornado import gen
    from tornado import ioloop
except ImportError:
    HAS_TORNADO = False
else:
    HAS_TORNADO = True


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: List[str] = []
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        self.messages.append(record.getMessage())


def _build_logger() -> Tuple[logging.Logger, _CaptureHandler]:
    logger = logging.Logger("bundle4-logger")
    logger.setLevel(logging.INFO)
    handler = _CaptureHandler()
    logger.addHandler(handler)
    return logger, handler


def _assert_identifier_fragments(message: str, identifier: Any) -> None:
    text = str(identifier).replace("\r\n", "\n").replace("\r", "\n")
    for fragment in [part for part in text.split("\n") if part]:
        assert fragment in message


_KNOWN_PLACEHOLDERS = ["<unknown>", "<unnamed>", "<none>", "<no name>"]


def _assert_no_generic_placeholder(messages: List[str]) -> None:
    """Verify messages don't use known generic placeholder strings as identifiers."""
    for message in messages:
        lowered = message.lower()
        for placeholder in _KNOWN_PLACEHOLDERS:
            assert placeholder not in lowered, (
                f"Message uses generic placeholder {placeholder!r}: {message!r}"
            )


def _assert_single_line(messages: List[str]) -> None:
    for message in messages:
        assert "\n" not in message
        assert "\r" not in message


def _assert_retry_label_records(
    records: List[logging.LogRecord], expected_label: str
) -> None:
    assert records
    for record in records:
        assert hasattr(record, "retry_label")
        assert record.retry_label == expected_label


def _assert_meaningful_retry_label_records(
    records: List[logging.LogRecord],
) -> str:
    assert records
    retry_label = getattr(records[0], "retry_label")
    assert isinstance(retry_label, str)
    assert retry_label.strip()
    lowered = retry_label.lower()
    for placeholder in _KNOWN_PLACEHOLDERS:
        assert placeholder not in lowered
    for record in records:
        assert getattr(record, "retry_label") == retry_label
    return retry_label


def _sync_no_sleep(_: float) -> None:
    return None


async def _async_no_sleep(_: float) -> None:
    return None


if HAS_TORNADO:

    @gen.coroutine
    def _tornado_no_sleep(_: float):
        return None


ALL_VARIANTS = [
    "sync",
    "async",
    pytest.param("tornado", marks=pytest.mark.skipif(not HAS_TORNADO, reason="tornado not installed")),
]
BLOCK_VARIANTS = [
    "sync",
    "async",
    pytest.param("tornado", marks=pytest.mark.skipif(not HAS_TORNADO, reason="tornado not installed")),
]


def _run_call(variant: str, retrying: Any, fn: Any) -> Any:
    if variant == "sync":
        return retrying(fn)
    if variant == "async":
        return asyncio.run(retrying(fn))
    if variant == "tornado":
        assert HAS_TORNADO
        loop = ioloop.IOLoop()
        try:
            return loop.run_sync(lambda: retrying(fn))
        finally:
            loop.close()
    raise AssertionError(f"unsupported variant: {variant}")


def _run_block_exception(variant: str, retrying: Any, message: str) -> None:
    if variant in ("sync", "tornado"):
        state = {"calls": 0}
        for attempt in retrying:
            with attempt:
                state["calls"] += 1
                if state["calls"] == 1:
                    raise ValueError(message)
        return

    async def _runner() -> None:
        state = {"calls": 0}
        async for attempt in retrying:
            with attempt:
                state["calls"] += 1
                if state["calls"] == 1:
                    raise ValueError(message)

    asyncio.run(_runner())


def _build_before_sleep_retrying(
    variant: str, logger: logging.Logger, label: Optional[str],
    block_path: bool = False,
) -> Any:
    kwargs: Dict[str, Any] = {
        "stop": stop_after_attempt(2),
        "wait": wait_fixed(0.01),
        "retry": retry_if_exception_type(ValueError),
        "before_sleep": tenacity.before_sleep_log(logger, logging.INFO),
    }
    if label is not None:
        kwargs["label"] = label

    if variant == "sync":
        kwargs["sleep"] = _sync_no_sleep
        return Retrying(**kwargs)
    if variant == "async":
        kwargs["sleep"] = _async_no_sleep
        return AsyncRetrying(**kwargs)
    if variant == "tornado":
        # Block-path uses inherited sync __iter__, so needs sync sleep
        kwargs["sleep"] = _sync_no_sleep if block_path else _tornado_no_sleep
        return tenacity.tornadoweb.TornadoRetrying(**kwargs)
    raise AssertionError(f"unsupported variant: {variant}")


def _build_log_retrying(
    variant: str, callback_kind: str, logger: logging.Logger, label: Optional[str],
    block_path: bool = False,
) -> Any:
    kwargs: Dict[str, Any] = {
        "stop": stop_after_attempt(2),
        "wait": wait_fixed(0.01),
        "retry": retry_if_exception_type(ValueError),
    }
    if callback_kind == "before":
        kwargs["before"] = tenacity.before_log(logger, logging.INFO)
    elif callback_kind == "after":
        kwargs["after"] = tenacity.after_log(logger, logging.INFO)
    else:
        raise AssertionError(f"unsupported callback kind: {callback_kind}")

    if label is not None:
        kwargs["label"] = label

    if variant == "sync":
        kwargs["sleep"] = _sync_no_sleep
        return Retrying(**kwargs)
    if variant == "async":
        kwargs["sleep"] = _async_no_sleep
        return AsyncRetrying(**kwargs)
    if variant == "tornado":
        kwargs["sleep"] = _sync_no_sleep if block_path else _tornado_no_sleep
        return tenacity.tornadoweb.TornadoRetrying(**kwargs)
    raise AssertionError(f"unsupported variant: {variant}")


def _build_compound_retrying(
    variant: str, logger: logging.Logger, label: Optional[str], block_path: bool = False
) -> Any:
    kwargs: Dict[str, Any] = {
        "stop": stop_after_attempt(2),
        "wait": wait_fixed(0.01),
        "retry": retry_if_exception_type(ValueError),
        "before": tenacity.before_log(logger, logging.INFO),
        "after": tenacity.after_log(logger, logging.INFO),
        "before_sleep": tenacity.before_sleep_log(logger, logging.INFO),
    }
    if label is not None:
        kwargs["label"] = label

    if variant == "sync":
        kwargs["sleep"] = _sync_no_sleep
        return Retrying(**kwargs)
    if variant == "async":
        kwargs["sleep"] = _async_no_sleep
        return AsyncRetrying(**kwargs)
    if variant == "tornado":
        kwargs["sleep"] = _sync_no_sleep if block_path else _tornado_no_sleep
        return tenacity.tornadoweb.TornadoRetrying(**kwargs)
    raise AssertionError(f"unsupported variant: {variant}")


def _make_failing_fn(variant: str, error_msg: str = "boom"):
    """Create a function that fails once then succeeds, for the given variant."""
    state = {"calls": 0}

    if variant == "sync":
        def fn() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                raise ValueError(error_msg)
            return "ok"
        return fn
    elif variant == "async":
        async def fn() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                raise ValueError(error_msg)
            return "ok"
        return fn
    else:
        @gen.coroutine
        def fn():
            state["calls"] += 1
            if state["calls"] == 1:
                raise ValueError(error_msg)
            return "ok"
        return fn


def _run_block_label_mutation_session(
    variant: str, retrying: Any, late_label: str, message: str
) -> None:
    if variant in ("sync", "tornado"):
        state = {"calls": 0}
        for attempt in retrying:
            with attempt:
                state["calls"] += 1
                if state["calls"] == 1:
                    retrying.label = late_label
                    raise ValueError(message)
        return

    async def _runner() -> None:
        state = {"calls": 0}
        async for attempt in retrying:
            with attempt:
                state["calls"] += 1
                if state["calls"] == 1:
                    retrying.label = late_label
                    raise ValueError(message)

    asyncio.run(_runner())


# ---------------------------------------------------------------------------
# Label on call path (before_sleep)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS)
@pytest.mark.parametrize("label", ["worker-A", "line1\nline2"])
def test_before_sleep_uses_label_on_call_path(variant: str, label: str) -> None:
    logger, handler = _build_logger()
    retrying = _build_before_sleep_retrying(variant, logger, label)
    fn = _make_failing_fn(variant, "boom\nline")
    _run_call(variant, retrying, fn)

    assert len(handler.messages) == 1
    message = handler.messages[0]
    _assert_identifier_fragments(message, label)
    _assert_single_line(handler.messages)
    _assert_retry_label_records(handler.records, label)


# ---------------------------------------------------------------------------
# Block path (before_sleep) -- no label provided
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", BLOCK_VARIANTS)
def test_before_sleep_block_path_uses_meaningful_identifier(variant: str) -> None:
    """When no callable is bound and no label is set, a meaningful identifier should appear."""
    logger, handler = _build_logger()
    retrying = _build_before_sleep_retrying(variant, logger, None, block_path=True)
    _run_block_exception(variant, retrying, "block\nerror")

    assert len(handler.messages) == 1
    message = handler.messages[0]
    assert len(message.strip()) > 0
    _assert_no_generic_placeholder(handler.messages)
    _assert_single_line(handler.messages)
    retry_label = _assert_meaningful_retry_label_records(handler.records)
    _assert_identifier_fragments(message, retry_label)


@pytest.mark.parametrize("variant", BLOCK_VARIANTS)
@pytest.mark.parametrize("label", ["block-A", "block\nline"])
def test_before_sleep_block_path_uses_label_when_provided(
    variant: str, label: str
) -> None:
    logger, handler = _build_logger()
    retrying = _build_before_sleep_retrying(variant, logger, label, block_path=True)
    _run_block_exception(variant, retrying, "block\nerror")

    assert len(handler.messages) == 1
    message = handler.messages[0]
    _assert_identifier_fragments(message, label)
    _assert_single_line(handler.messages)
    _assert_retry_label_records(handler.records, label)


# ---------------------------------------------------------------------------
# Block path (before / after) -- no label provided
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", BLOCK_VARIANTS)
@pytest.mark.parametrize("callback_kind", ["before", "after"])
def test_before_and_after_log_block_path_meaningful_identifier(
    variant: str, callback_kind: str
) -> None:
    """before_log and after_log should also use a meaningful identifier in block paths."""
    logger, handler = _build_logger()
    retrying = _build_log_retrying(variant, callback_kind, logger, None, block_path=True)
    _run_block_exception(variant, retrying, "block")

    assert handler.messages
    _assert_no_generic_placeholder(handler.messages)
    _assert_single_line(handler.messages)
    retry_label = _assert_meaningful_retry_label_records(handler.records)
    for message in handler.messages:
        _assert_identifier_fragments(message, retry_label)


@pytest.mark.parametrize("variant", BLOCK_VARIANTS)
@pytest.mark.parametrize("callback_kind", ["before", "after"])
@pytest.mark.parametrize("label", ["block\nid"])
def test_before_and_after_log_block_path_uses_label(
    variant: str, callback_kind: str, label: str
) -> None:
    logger, handler = _build_logger()
    retrying = _build_log_retrying(variant, callback_kind, logger, label, block_path=True)
    _run_block_exception(variant, retrying, "block")

    assert handler.messages
    for message in handler.messages:
        _assert_identifier_fragments(message, label)
    _assert_single_line(handler.messages)
    _assert_retry_label_records(handler.records, label)


# ---------------------------------------------------------------------------
# copy() / retry_with() preserve or override label
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS)
@pytest.mark.parametrize(
    ("override_label", "expected_label"),
    [
        (None, "base-label"),
        ("override-label", "override-label"),
    ],
)
def test_copy_preserves_or_overrides_label(
    variant: str, override_label: Optional[str], expected_label: str
) -> None:
    logger, handler = _build_logger()
    retrying = _build_before_sleep_retrying(variant, logger, "base-label")
    if override_label is None:
        copied = retrying.copy()
    else:
        copied = retrying.copy(label=override_label)

    fn = _make_failing_fn(variant, "copy")
    _run_call(variant, copied, fn)

    assert len(handler.messages) == 1
    assert expected_label in handler.messages[0]
    _assert_retry_label_records(handler.records, expected_label)


@pytest.mark.parametrize("variant", ALL_VARIANTS)
@pytest.mark.parametrize(
    ("override_label", "expected_label"),
    [
        (None, "decorator-base"),
        ("decorator-override", "decorator-override"),
    ],
)
def test_retry_with_preserves_or_overrides_label(
    variant: str, override_label: Optional[str], expected_label: str
) -> None:
    logger, handler = _build_logger()

    if variant == "sync":
        state = {"calls": 0}

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(0.01),
            sleep=_sync_no_sleep,
            retry=retry_if_exception_type(ValueError),
            before_sleep=tenacity.before_sleep_log(logger, logging.INFO),
            label="decorator-base",
        )
        def wrapped_call() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                raise ValueError("sync")
            return "ok"

        target = wrapped_call.retry_with() if override_label is None else wrapped_call.retry_with(label=override_label)  # type: ignore[attr-defined]
        target()
    elif variant == "async":
        state = {"calls": 0}

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(0.01),
            sleep=_async_no_sleep,
            retry=retry_if_exception_type(ValueError),
            before_sleep=tenacity.before_sleep_log(logger, logging.INFO),
            label="decorator-base",
        )
        async def wrapped_call() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                raise ValueError("async")
            return "ok"

        target = wrapped_call.retry_with() if override_label is None else wrapped_call.retry_with(label=override_label)  # type: ignore[attr-defined]
        asyncio.run(target())
    else:
        state = {"calls": 0}

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(0.01),
            sleep=_tornado_no_sleep,
            retry=retry_if_exception_type(ValueError),
            before_sleep=tenacity.before_sleep_log(logger, logging.INFO),
            label="decorator-base",
        )
        @gen.coroutine
        def wrapped_call():
            state["calls"] += 1
            if state["calls"] == 1:
                raise ValueError("tornado")
            return "ok"

        target = wrapped_call.retry_with() if override_label is None else wrapped_call.retry_with(label=override_label)  # type: ignore[attr-defined]
        loop = ioloop.IOLoop()
        try:
            loop.run_sync(target)
        finally:
            loop.close()

    assert len(handler.messages) == 1
    assert expected_label in handler.messages[0]
    _assert_retry_label_records(handler.records, expected_label)


# ---------------------------------------------------------------------------
# before / after log with label on call path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS)
@pytest.mark.parametrize("callback_kind", ["before", "after"])
@pytest.mark.parametrize("label", ["job-A", "job\nid"])
def test_before_and_after_log_use_label_on_call_path(
    variant: str, callback_kind: str, label: str
) -> None:
    logger, handler = _build_logger()
    retrying = _build_log_retrying(variant, callback_kind, logger, label)
    fn = _make_failing_fn(variant, "fail")
    _run_call(variant, retrying, fn)

    assert handler.messages
    for message in handler.messages:
        _assert_identifier_fragments(message, label)
    _assert_single_line(handler.messages)
    _assert_retry_label_records(handler.records, label)


# ---------------------------------------------------------------------------
# Identifier capture boundary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_inflight_explicit_label_mutation_only_affects_future_calls(variant: str) -> None:
    logger, handler = _build_logger()
    original_label = "alphaq9\nbravoq9"
    updated_label = "omegar8\ndeltar8"
    retrying = _build_compound_retrying(variant, logger, original_label)
    state = {"calls": 0}

    if variant == "sync":

        def mutate_label_then_fail() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                retrying.label = updated_label
                raise ValueError("first")
            return "ok"

        _run_call(variant, retrying, mutate_label_then_fail)
    elif variant == "async":

        async def mutate_label_then_fail() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                retrying.label = updated_label
                raise ValueError("first")
            return "ok"

        _run_call(variant, retrying, mutate_label_then_fail)
    else:

        @gen.coroutine
        def mutate_label_then_fail():
            state["calls"] += 1
            if state["calls"] == 1:
                retrying.label = updated_label
                raise ValueError("first")
            return "ok"

        _run_call(variant, retrying, mutate_label_then_fail)

    assert handler.messages
    for message in handler.messages:
        _assert_identifier_fragments(message, original_label)
        assert "omegar8" not in message
        assert "deltar8" not in message
    _assert_single_line(handler.messages)
    _assert_retry_label_records(handler.records, original_label)

    handler.messages.clear()
    handler.records.clear()
    _run_call(variant, retrying, _make_failing_fn(variant, "second"))

    assert handler.messages
    for message in handler.messages:
        _assert_identifier_fragments(message, updated_label)
    _assert_retry_label_records(handler.records, updated_label)


@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_inflight_call_path_identifier_mutation_only_affects_future_calls(
    variant: str,
) -> None:
    logger, handler = _build_logger()
    updated_label = "latecallp3\nmarkerp3"
    retrying = _build_compound_retrying(variant, logger, None)
    state = {"calls": 0}

    if variant == "sync":

        def call_identifier_probe_q7m() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                retrying.label = updated_label
                raise ValueError("first")
            return "ok"

        original_identifier = tenacity._utils.get_callback_name(call_identifier_probe_q7m)
        _run_call(variant, retrying, call_identifier_probe_q7m)
    elif variant == "async":

        async def call_identifier_probe_q7m() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                retrying.label = updated_label
                raise ValueError("first")
            return "ok"

        original_identifier = tenacity._utils.get_callback_name(call_identifier_probe_q7m)
        _run_call(variant, retrying, call_identifier_probe_q7m)
    else:

        @gen.coroutine
        def call_identifier_probe_q7m():
            state["calls"] += 1
            if state["calls"] == 1:
                retrying.label = updated_label
                raise ValueError("first")
            return "ok"

        original_identifier = tenacity._utils.get_callback_name(call_identifier_probe_q7m)
        _run_call(variant, retrying, call_identifier_probe_q7m)

    assert handler.messages
    for message in handler.messages:
        assert "call_identifier_probe_q7m" in message
        assert "latecallp3" not in message
        assert "markerp3" not in message
    _assert_single_line(handler.messages)
    _assert_retry_label_records(handler.records, original_identifier)

    handler.messages.clear()
    handler.records.clear()
    _run_call(variant, retrying, _make_failing_fn(variant, "second"))

    assert handler.messages
    for message in handler.messages:
        _assert_identifier_fragments(message, updated_label)
    _assert_retry_label_records(handler.records, updated_label)


@pytest.mark.parametrize("variant", BLOCK_VARIANTS)
def test_inflight_block_identifier_mutation_only_affects_future_sessions(
    variant: str,
) -> None:
    logger, handler = _build_logger()
    updated_label = "lateblockk4\nmarkerk4"
    retrying = _build_compound_retrying(variant, logger, None, block_path=True)

    _run_block_label_mutation_session(variant, retrying, updated_label, "first")

    assert handler.messages
    _assert_no_generic_placeholder(handler.messages)
    _assert_single_line(handler.messages)
    original_retry_label = _assert_meaningful_retry_label_records(handler.records)
    for message in handler.messages:
        assert "lateblockk4" not in message
        assert "markerk4" not in message
        _assert_identifier_fragments(message, original_retry_label)

    handler.messages.clear()
    handler.records.clear()
    _run_block_exception(variant, retrying, "second")

    assert handler.messages
    for message in handler.messages:
        _assert_identifier_fragments(message, updated_label)
    _assert_retry_label_records(handler.records, updated_label)


# ---------------------------------------------------------------------------
# Multiline return value escaping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_before_sleep_log_escapes_multiline_return_values(variant: str) -> None:
    logger, handler = _build_logger()
    kwargs: Dict[str, Any] = {
        "stop": stop_after_attempt(2),
        "wait": wait_fixed(0.01),
        "retry": retry_if_result(lambda value: value == "line1\nline2"),
        "before_sleep": tenacity.before_sleep_log(logger, logging.INFO),
    }
    if variant == "sync":
        kwargs["sleep"] = _sync_no_sleep
        retrying = Retrying(**kwargs)
        state = {"calls": 0}

        def retry_on_result() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                return "line1\nline2"
            return "done"

        _run_call(variant, retrying, retry_on_result)
    elif variant == "async":
        kwargs["sleep"] = _async_no_sleep
        retrying = AsyncRetrying(**kwargs)
        state = {"calls": 0}

        async def retry_on_result() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                return "line1\nline2"
            return "done"

        _run_call(variant, retrying, retry_on_result)
    else:
        kwargs["sleep"] = _tornado_no_sleep
        retrying = tenacity.tornadoweb.TornadoRetrying(**kwargs)
        state = {"calls": 0}

        @gen.coroutine
        def retry_on_result():
            state["calls"] += 1
            if state["calls"] == 1:
                return "line1\nline2"
            return "done"

        _run_call(variant, retrying, retry_on_result)

    assert len(handler.messages) == 1
    assert "line1" in handler.messages[0]
    assert "line2" in handler.messages[0]
    _assert_single_line(handler.messages)


# ---------------------------------------------------------------------------
# Multiline exception message escaping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_before_sleep_log_escapes_multiline_exception_messages(variant: str) -> None:
    logger, handler = _build_logger()
    retrying = _build_before_sleep_retrying(variant, logger, "esc-test")
    fn = _make_failing_fn(variant, "error\ndetails\nmore")
    _run_call(variant, retrying, fn)

    assert len(handler.messages) == 1
    message = handler.messages[0]
    assert "error" in message
    assert "details" in message
    _assert_single_line(handler.messages)


# ---------------------------------------------------------------------------
# Carriage return escaping (\r and \r\n)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_before_sleep_log_escapes_carriage_returns(variant: str) -> None:
    logger, handler = _build_logger()
    retrying = _build_before_sleep_retrying(variant, logger, "cr-test")
    fn = _make_failing_fn(variant, "part1\r\npart2\rpart3")
    _run_call(variant, retrying, fn)

    assert len(handler.messages) == 1
    message = handler.messages[0]
    assert "part1" in message
    assert "part2" in message
    assert "part3" in message
    _assert_single_line(handler.messages)


# ---------------------------------------------------------------------------
# after_log single-line with multiline result
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_after_log_single_line_with_multiline_label(variant: str) -> None:
    """after_log should remain single-line even when the label contains newlines."""
    logger, handler = _build_logger()
    label = "after\nlog\rtest"
    retrying = _build_log_retrying(variant, "after", logger, label)
    fn = _make_failing_fn(variant, "fail")
    _run_call(variant, retrying, fn)

    assert handler.messages
    _assert_identifier_fragments(handler.messages[0], label)
    _assert_single_line(handler.messages)
    _assert_retry_label_records(handler.records, label)


# ---------------------------------------------------------------------------
# copy preserves label for block path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", BLOCK_VARIANTS)
def test_copy_preserves_label_for_block_path(variant: str) -> None:
    logger, handler = _build_logger()
    original = _build_before_sleep_retrying(variant, logger, "block-copy", block_path=True)
    copied = original.copy()
    _run_block_exception(variant, copied, "copy")
    _assert_single_line(handler.messages)
    assert len(handler.messages) == 1
    assert "block-copy" in handler.messages[0]
    _assert_retry_label_records(handler.records, "block-copy")


# ---------------------------------------------------------------------------
# __repr__ includes label
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_repr_includes_label(variant: str) -> None:
    """The string representation of a retry controller should include the label."""
    if variant == "sync":
        r = Retrying(label="my-label", sleep=_sync_no_sleep)
    elif variant == "async":
        r = AsyncRetrying(label="my-label", sleep=_async_no_sleep)
    else:
        r = tenacity.tornadoweb.TornadoRetrying(label="my-label", sleep=_tornado_no_sleep)
    text = repr(r)
    assert "my-label" in text


# ---------------------------------------------------------------------------
# Empty string label (falsy-but-not-None) -- label="" should be used, not
# fall back to function name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_empty_string_label_is_used_not_function_name(variant: str) -> None:
    """An empty-string label is a valid label; callbacks should NOT fall back to fn name."""
    logger, handler = _build_logger()
    kwargs: Dict[str, Any] = {
        "stop": stop_after_attempt(2),
        "wait": wait_fixed(0.01),
        "retry": retry_if_exception_type(ValueError),
        "before": tenacity.before_log(logger, logging.INFO),
        "label": "",
    }

    state = {"calls": 0}

    if variant == "sync":
        kwargs["sleep"] = _sync_no_sleep
        retrying = Retrying(**kwargs)

        def distinctive_target_xq9() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                raise ValueError("test")
            return "ok"

        _run_call(variant, retrying, distinctive_target_xq9)
    elif variant == "async":
        kwargs["sleep"] = _async_no_sleep
        retrying = AsyncRetrying(**kwargs)

        async def distinctive_target_xq9() -> str:
            state["calls"] += 1
            if state["calls"] == 1:
                raise ValueError("test")
            return "ok"

        _run_call(variant, retrying, distinctive_target_xq9)
    else:
        kwargs["sleep"] = _tornado_no_sleep
        retrying = tenacity.tornadoweb.TornadoRetrying(**kwargs)

        @gen.coroutine
        def distinctive_target_xq9():
            state["calls"] += 1
            if state["calls"] == 1:
                raise ValueError("test")
            return "ok"

        _run_call(variant, retrying, distinctive_target_xq9)

    assert handler.messages
    for message in handler.messages:
        # The function name should NOT appear since label="" was explicitly set
        assert "distinctive_target_xq9" not in message
    _assert_retry_label_records(handler.records, "")


# ---------------------------------------------------------------------------
# Compound test: all three callbacks (before + after + before_sleep) with label
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_all_callbacks_use_label_simultaneously(variant: str) -> None:
    """When before, after, and before_sleep are all set, all should use the label."""
    logger, handler = _build_logger()
    label = "compound-test"
    kwargs: Dict[str, Any] = {
        "stop": stop_after_attempt(2),
        "wait": wait_fixed(0.01),
        "retry": retry_if_exception_type(ValueError),
        "before": tenacity.before_log(logger, logging.INFO),
        "after": tenacity.after_log(logger, logging.INFO),
        "before_sleep": tenacity.before_sleep_log(logger, logging.INFO),
        "label": label,
    }
    if variant == "sync":
        kwargs["sleep"] = _sync_no_sleep
        retrying = Retrying(**kwargs)
    elif variant == "async":
        kwargs["sleep"] = _async_no_sleep
        retrying = AsyncRetrying(**kwargs)
    else:
        kwargs["sleep"] = _tornado_no_sleep
        retrying = tenacity.tornadoweb.TornadoRetrying(**kwargs)

    fn = _make_failing_fn(variant, "compound")
    _run_call(variant, retrying, fn)

    # before fires twice (attempt 1 + attempt 2), after fires twice,
    # before_sleep fires once (between attempt 1 and 2)
    assert len(handler.messages) >= 3
    for message in handler.messages:
        assert label in message
    _assert_retry_label_records(handler.records, label)


# ---------------------------------------------------------------------------
# Label with multiline content in __repr__
# ---------------------------------------------------------------------------

def test_repr_with_multiline_label() -> None:
    """Labels with newlines should still produce valid repr output."""
    r = Retrying(label="line1\nline2", sleep=_sync_no_sleep)
    text = repr(r)
    assert "line1" in text
    assert "line2" in text
