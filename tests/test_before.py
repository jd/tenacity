import logging
import random
import unittest.mock

from tenacity import before_log
from tenacity import _utils  # noqa

from . import test_tenacity


class TestBeforeLogFormat(unittest.TestCase):
    def setUp(self) -> None:
        self.log_level = random.choice((logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL))
        self.previous_attempt_number = random.randint(1, 512)

    def test_01_default(self):
        """Test log formatting."""
        log = unittest.mock.MagicMock(spec="logging.Logger.log")
        logger = unittest.mock.MagicMock(spec="logging.Logger", log=log)

        delay_since_first_attempt = 0.1

        retry_state = test_tenacity.make_retry_state(self.previous_attempt_number, delay_since_first_attempt)
        fun = before_log(logger=logger, log_level=self.log_level)
        fun(retry_state)
        log.assert_called_once_with(
            self.log_level,
            f"Starting call to '{_utils.get_callback_name(retry_state.fn)}', "
            f"this is the {_utils.to_ordinal(retry_state.attempt_number)} time calling it.",
        )

    def test_02_no_call_function(self):
        """Test log formatting when there is no called function.

        E.g. when using as context manager.
        """
        log = unittest.mock.MagicMock(spec="logging.Logger.log")
        logger = unittest.mock.MagicMock(spec="logging.Logger", log=log)

        delay_since_first_attempt = 0.1

        retry_state = test_tenacity.make_retry_state(self.previous_attempt_number, delay_since_first_attempt)
        retry_state.fn = None
        fun = before_log(logger=logger, log_level=self.log_level)
        fun(retry_state)
        log.assert_called_once_with(
            self.log_level,
            f"Starting block, this is the {_utils.to_ordinal(retry_state.attempt_number)} time running it.",
        )
