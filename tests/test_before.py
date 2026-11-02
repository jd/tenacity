import unittest

from tenacity import before_nothing

from . import test_tenacity


class TestBeforeNothing(unittest.TestCase):
    def test_before_nothing_does_not_raise(self) -> None:
        retry_state = test_tenacity.make_retry_state(1, 0.1)
        before_nothing(retry_state)
