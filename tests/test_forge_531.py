# Regression test for forge issue #531
#
# Bug: The `after` callback is not called on the final successful attempt.
# In BaseRetrying._post_retry_check_actions, when the function succeeds and
# no retry is needed (retry_run_result is False), the code takes an early
# return and never invokes the `after` callback.  The `after` callback is only
# called when a retry is about to happen.  This means users cannot use `after`
# to log a "retry_success" message when a function eventually succeeds after
# one or more failures.

import pytest

from tenacity import (
    RetryCallState,
    Retrying,
    stop_after_attempt,
    wait_fixed,
    retry_if_exception_type,
)


def test_after_callback_called_on_final_success_after_retry():
    """The `after` callback must be invoked on every attempt, including the
    final successful one that follows a failed attempt."""

    after_calls = []

    def after_cb(retry_state: RetryCallState) -> None:
        after_calls.append({
            "attempt": retry_state.attempt_number,
            "failed": retry_state.outcome.failed if retry_state.outcome else None,
        })

    attempts = {"count": 0}

    def might_fail():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ValueError("fail first")
        return "ok"

    r = Retrying(
        wait=wait_fixed(0),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(ValueError),
        after=after_cb,
        reraise=True,
    )
    result = r(might_fail)

    assert result == "ok"
    # The function was attempted twice: once failed, once succeeded.
    assert attempts["count"] == 2
    # The `after` callback should have been called for BOTH attempts:
    #   - attempt 1 (failed, retry triggered)
    #   - attempt 2 (succeeded, no retry needed)
    # Bug: currently `after` is only called when a retry is about to happen,
    # so the successful attempt 2 is missing from after_calls.
    assert len(after_calls) == 2, (
        f"Expected `after` to be called 2 times (once per attempt), "
        f"but it was called {len(after_calls)} times: {after_calls}"
    )
    # The last call should correspond to the successful attempt.
    assert after_calls[-1]["failed"] is False