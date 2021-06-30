import logging
import random
import unittest.mock

from tenacity import after_log
from tenacity import _utils  # noqa

from . import test_tenacity


class TestAfterLogFormat(unittest.TestCase):
    def setUp(self) -> None:
        self.log_level = random.choice((logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL))
        self.previous_attempt_number = random.randint(1, 512)

    def test_01_default(self):
        """Test log formatting."""
        log = unittest.mock.MagicMock(spec="logging.Logger.log")
        logger = unittest.mock.MagicMock(spec="logging.Logger", log=log)

        sec_format = "%0.3f"
        delay_since_first_attempt = 0.1

        retry_state = test_tenacity.make_retry_state(self.previous_attempt_number, delay_since_first_attempt)
        fun = after_log(logger=logger, log_level=self.log_level)  # use default sec_format
        fun(retry_state)
        log.assert_called_once_with(
            self.log_level,
            f"Finished call to '{_utils.get_callback_name(retry_state.fn)}' "
            f"after {sec_format % retry_state.seconds_since_start}(s), "
            f"this was the {_utils.to_ordinal(retry_state.attempt_number)} time calling it.",
        )

    def test_02_custom_sec_format(self):
        """Test log formatting with custom int format.."""
        log = unittest.mock.MagicMock(spec="logging.Logger.log")
        logger = unittest.mock.MagicMock(spec="logging.Logger", log=log)

        sec_format = "%.1f"
        delay_since_first_attempt = 0.1

        retry_state = test_tenacity.make_retry_state(self.previous_attempt_number, delay_since_first_attempt)
        fun = after_log(logger=logger, log_level=self.log_level, sec_format=sec_format)
        fun(retry_state)
        log.assert_called_once_with(
            self.log_level,
            f"Finished call to '{_utils.get_callback_name(retry_state.fn)}' "
            f"after {sec_format % retry_state.seconds_since_start}(s), "
            f"this was the {_utils.to_ordinal(retry_state.attempt_number)} time calling it.",
        )
