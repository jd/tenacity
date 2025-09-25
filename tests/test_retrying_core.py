import pytest
from tenacity import (
    retry, Retrying,
    stop_after_attempt, stop_after_delay,
    wait_fixed, wait_exponential,
    retry_if_exception_type, retry_if_result
)

def no_sleep(_seconds: float) -> None:
    return

def test_success_after_retries_on_exception():
    calls = {"n": 0}

    @retry(
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(ValueError),
        wait=wait_fixed(0),
        reraise=True,
        sleep=no_sleep,
    )
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("temporary")
        return "OK"

    result = flaky()
    assert result == "OK"
    assert calls["n"] == 3

def test_reraise_on_exhausted_attempts():
    @retry(
        stop=stop_after_attempt(2),
        retry=retry_if_exception_type(RuntimeError),
        wait=wait_fixed(0),
        reraise=True,
        sleep=no_sleep,
    )
    def always_fails():
        raise RuntimeError("bad")

    with pytest.raises(RuntimeError):
        always_fails()

def test_stop_after_delay_boundary():
    attempts = {"n": 0}
    r = Retrying(
        stop=stop_after_delay(0.01),
        wait=wait_fixed(0),
        retry=retry_if_exception_type(ValueError),
        reraise=False,
        sleep=no_sleep,
    )
    def fn():
        attempts["n"] += 1
        raise ValueError("still failing")

    with pytest.raises(ValueError):
        r(fn)
    assert attempts["n"] >= 1

def test_retry_on_result_predicate():
    results = iter([None, None, 42])

    @retry(
        stop=stop_after_attempt(5),
        retry=retry_if_result(lambda x: x is None),
        wait=wait_fixed(0),
        reraise=True,
        sleep=no_sleep,
    )
    def maybe_none():
        return next(results)

    value = maybe_none()
    assert value == 42

def test_before_after_callbacks_called_in_order():
    events = []

    def before_fn(retry_state):
        events.append(("before", retry_state.attempt_number))

    def after_fn(retry_state):
        exc = retry_state.outcome.exception()
        events.append(("after", retry_state.attempt_number, type(exc).__name__ if exc else None))

    @retry(
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(KeyError),
        wait=wait_fixed(0),
        before=before_fn,
        after=after_fn,
        reraise=False,
        sleep=no_sleep,
    )
    def will_fail_then_fail_then_succeed():
        if len([e for e in events if e[0] == "after"]) < 2:
            raise KeyError("nope")
        return "done"

    result = will_fail_then_fail_then_succeed()
    assert result == "done"
    assert events[0][0] == "before"
    assert events[1][0] == "after"
    assert events[1][2] == "KeyError"

def test_wait_exponential_caps_sleep_without_jitter():
    sleeps = []
    def record_sleep(seconds):
        sleeps.append(seconds)

    @retry(
        stop=stop_after_attempt(4),
        retry=retry_if_exception_type(ValueError),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=False,
        sleep=record_sleep,
    )
    def always_fail():
        raise ValueError("x")

    with pytest.raises(ValueError):
        always_fail()
    assert sleeps[:3] == [1, 2, 4]

def test_non_retryable_exception_bubbles_immediately():
    calls = {"n": 0}

    @retry(
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(ValueError),
        wait=wait_fixed(0),
        reraise=True,
        sleep=no_sleep,
    )
    def raises_type_error():
        calls["n"] += 1
        raise TypeError("do not retry this")

    with pytest.raises(TypeError):
        raises_type_error()
    assert calls["n"] == 1
