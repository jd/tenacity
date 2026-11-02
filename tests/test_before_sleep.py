import unittest

from tenacity import before_sleep_nothing

from . import test_tenacity


class TestBeforeSleepNothing(unittest.TestCase):
    def test_before_sleep_nothing_does_not_raise(self) -> None:
        retry_state = test_tenacity.make_retry_state(1, 0.1)
        before_sleep_nothing(retry_state)
