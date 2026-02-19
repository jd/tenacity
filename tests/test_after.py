import logging
import random
import unittest.mock

from tenacity import (
    _utils,
    after_log,
)

from . import test_tenacity


class TestAfterLogFormat(unittest.TestCase):
    def setUp(self) -> None:
        self.log_level = random.choice(
            (
                logging.DEBUG,
                logging.INFO,
                logging.WARNING,
                logging.ERROR,
                logging.CRITICAL,
            )
        )
        self.previous_attempt_number = random.randint(1, 512)

    def test_01_default(self) -> None:
        """Test log formatting."""
        log = unittest.mock.MagicMock(spec="logging.Logger.log")
        logger = unittest.mock.MagicMock(spec="logging.Logger", log=log)

        sec_format = "%.3g"
        delay_since_first_attempt = 0.1

        retry_state = test_tenacity.make_retry_state(
            self.previous_attempt_number, delay_since_first_attempt
        )
        fun = after_log(
            logger=logger, log_level=self.log_level
        )  # use default sec_format
        fun(retry_state)
        fn_name = (
            "<unknown>"
            if retry_state.fn is None
            else _utils.get_callback_name(retry_state.fn)
        )
        log.assert_called_once_with(
            self.log_level,
            f"Finished call to '{fn_name}' "
            f"after {sec_format % retry_state.seconds_since_start}(s), "
            f"this was the {_utils.to_ordinal(retry_state.attempt_number)} time calling it.",
        )

    def test_02_none_seconds_since_start(self) -> None:
        """Test log formatting when seconds_since_start is None."""
        log = unittest.mock.MagicMock(spec="logging.Logger.log")
        logger = unittest.mock.MagicMock(spec="logging.Logger", log=log)

        retry_state = test_tenacity.make_retry_state(self.previous_attempt_number, 0.1)
        retry_state.outcome_timestamp = None
        assert retry_state.seconds_since_start is None

        fun = after_log(logger=logger, log_level=self.log_level)
        fun(retry_state)
        fn_name = (
            "<unknown>"
            if retry_state.fn is None
            else _utils.get_callback_name(retry_state.fn)
        )
        log.assert_called_once_with(
            self.log_level,
            f"Finished call to '{fn_name}' "
            f"after ?(s), "
            f"this was the {_utils.to_ordinal(retry_state.attempt_number)} time calling it.",
        )

    def test_02_custom_sec_format(self) -> None:
        """Test log formatting with custom int format.."""
        log = unittest.mock.MagicMock(spec="logging.Logger.log")
        logger = unittest.mock.MagicMock(spec="logging.Logger", log=log)

        sec_format = "%.1f"
        delay_since_first_attempt = 0.1

        retry_state = test_tenacity.make_retry_state(
            self.previous_attempt_number, delay_since_first_attempt
        )
        fun = after_log(logger=logger, log_level=self.log_level, sec_format=sec_format)
        fun(retry_state)
        fn_name = (
            "<unknown>"
            if retry_state.fn is None
            else _utils.get_callback_name(retry_state.fn)
        )
        log.assert_called_once_with(
            self.log_level,
            f"Finished call to '{fn_name}' "
            f"after {sec_format % retry_state.seconds_since_start}(s), "
            f"this was the {_utils.to_ordinal(retry_state.attempt_number)} time calling it.",
        )
