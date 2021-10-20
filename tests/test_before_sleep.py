import logging
import random
import unittest.mock

from tenacity import before_sleep_log
from tenacity import _utils  # noqa

from . import test_tenacity


class TestBeforeSleepLogFormat(unittest.TestCase):
    def setUp(self) -> None:
        self.log_level = random.choice((logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL))
        self.previous_attempt_number = random.randint(1, 512)

    def test_01_failed(self):
        """Test log formatting."""
        log = unittest.mock.MagicMock(spec="logging.Logger.log")
        logger = unittest.mock.MagicMock(spec="logging.Logger", log=log)

        delay_since_first_attempt = 0.1
        sleep = 2

        retry_state = test_tenacity.make_retry_state(self.previous_attempt_number, delay_since_first_attempt)
        retry_state.next_action = unittest.mock.MagicMock(spec="tenacity.RetryAction", sleep=sleep)
        retry_state.outcome = unittest.mock.MagicMock(
            spec="tenacity.Future",
            failed=True,
            exception=unittest.mock.Mock(return_value=FileNotFoundError("Not found")),
        )
        fun = before_sleep_log(logger=logger, log_level=self.log_level)
        fun(retry_state)
        log.assert_called_once_with(
            self.log_level,
            f"Retrying {_utils.get_callback_name(retry_state.fn)} "
            f"in {sleep} seconds as it raised "
            f"{retry_state.outcome.exception().__class__.__name__}: {retry_state.outcome.exception()}.",
            exc_info=False,
        )

    def test_02_wrong_return(self):
        """Test log formatting."""
        log = unittest.mock.MagicMock(spec="logging.Logger.log")
        logger = unittest.mock.MagicMock(spec="logging.Logger", log=log)

        delay_since_first_attempt = 0.1
        sleep = 2

        retry_state = test_tenacity.make_retry_state(self.previous_attempt_number, delay_since_first_attempt)
        retry_state.next_action = unittest.mock.MagicMock(spec="tenacity.RetryAction", sleep=sleep)
        retry_state.outcome = unittest.mock.MagicMock(
            spec="tenacity.Future",
            failed=False,
            result=unittest.mock.Mock(return_value="infinity"),
        )
        fun = before_sleep_log(logger=logger, log_level=self.log_level)
        fun(retry_state)
        log.assert_called_once_with(
            self.log_level,
            f"Retrying {_utils.get_callback_name(retry_state.fn)} "
            f"in {sleep} seconds as it returned {retry_state.outcome.result()}.",
            exc_info=False,
        )
