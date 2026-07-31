"""Tests for the success callback / success_log helper (#531)."""

from __future__ import annotations

import logging
import unittest
import unittest.mock

from tenacity import (
    _utils,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    success_log,
    wait_none,
)

from . import test_tenacity


class TestSuccessCallback(unittest.TestCase):
    def test_success_fires_after_retry_recovery(self) -> None:
        calls: list[int] = []

        @retry(
            stop=stop_after_attempt(5),
            wait=wait_none(),
            retry=retry_if_exception_type(ValueError),
            success=lambda rs: calls.append(rs.attempt_number),
            reraise=True,
        )
        def flaky(n: list[int] = [0]) -> str:  # noqa: B006
            n[0] += 1
            if n[0] < 3:
                raise ValueError("not yet")
            return "ok"

        self.assertEqual(flaky(), "ok")
        self.assertEqual(calls, [3])

    def test_success_fires_on_first_try(self) -> None:
        calls: list[int] = []

        @retry(
            stop=stop_after_attempt(3),
            success=lambda rs: calls.append(rs.attempt_number),
        )
        def ok() -> str:
            return "ok"

        self.assertEqual(ok(), "ok")
        self.assertEqual(calls, [1])

    def test_success_not_called_when_exhausted(self) -> None:
        calls: list[int] = []

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_none(),
            retry=retry_if_exception_type(ValueError),
            success=lambda rs: calls.append(rs.attempt_number),
            reraise=True,
        )
        def always_fail() -> None:
            raise ValueError("nope")

        with self.assertRaises(ValueError):
            always_fail()
        self.assertEqual(calls, [])

    def test_after_still_only_on_failed_attempts(self) -> None:
        """Regression: ``after`` must not suddenly fire on success."""
        after_calls: list[int] = []
        success_calls: list[int] = []

        @retry(
            stop=stop_after_attempt(5),
            wait=wait_none(),
            retry=retry_if_exception_type(ValueError),
            after=lambda rs: after_calls.append(rs.attempt_number),
            success=lambda rs: success_calls.append(rs.attempt_number),
            reraise=True,
        )
        def flaky(n: list[int] = [0]) -> str:  # noqa: B006
            n[0] += 1
            if n[0] < 2:
                raise ValueError("x")
            return "ok"

        self.assertEqual(flaky(), "ok")
        # after runs once for the failed attempt that will be retried
        self.assertEqual(after_calls, [1])
        self.assertEqual(success_calls, [2])


class TestSuccessLog(unittest.TestCase):
    def test_only_if_retried_skips_first_try(self) -> None:
        log = unittest.mock.MagicMock(spec="logging.Logger.log")
        logger = unittest.mock.MagicMock(spec="logging.Logger", log=log)
        from tenacity import Future

        rs = test_tenacity.make_retry_state(1, 0.05)
        fut = Future(1)
        fut.set_result("ok")
        rs.outcome = fut
        rs.outcome_timestamp = rs.start_time + 0.05

        success_log(logger, logging.INFO)(rs)
        log.assert_not_called()

        success_log(logger, logging.INFO, only_if_retried=False)(rs)
        log.assert_called_once()
        msg = log.call_args[0][1]
        self.assertIn("Successful call", msg)
        self.assertIn(_utils.to_ordinal(1), msg)

    def test_logs_when_recovered(self) -> None:
        log = unittest.mock.MagicMock(spec="logging.Logger.log")
        logger = unittest.mock.MagicMock(spec="logging.Logger", log=log)
        rs = test_tenacity.make_retry_state(3, 0.2)
        from tenacity import Future

        fut = Future(3)
        fut.set_result("ok")
        rs.outcome = fut
        rs.outcome_timestamp = rs.start_time + 0.2

        success_log(logger, logging.INFO)(rs)
        log.assert_called_once()
        msg = log.call_args[0][1]
        self.assertIn("Successful call", msg)
        self.assertIn(_utils.to_ordinal(3), msg)


if __name__ == "__main__":
    unittest.main()
