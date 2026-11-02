import threading
import unittest
import unittest.mock

from tenacity import nap


class TestSleep(unittest.TestCase):
    def test_sleep_delegates_to_time_sleep(self) -> None:
        with unittest.mock.patch("tenacity.nap.time.sleep") as mock_sleep:
            nap.sleep(1.5)
        mock_sleep.assert_called_once_with(1.5)


class TestSleepUsingEvent(unittest.TestCase):
    def test_waits_on_event_with_given_timeout(self) -> None:
        event = unittest.mock.MagicMock(spec=threading.Event)
        strategy = nap.sleep_using_event(event)

        strategy(5)

        event.wait.assert_called_once_with(timeout=5)

    def test_waits_on_event_with_none_timeout(self) -> None:
        event = unittest.mock.MagicMock(spec=threading.Event)
        strategy = nap.sleep_using_event(event)

        strategy(None)

        event.wait.assert_called_once_with(timeout=None)

    def test_returns_early_when_event_already_set(self) -> None:
        # threading.Event.wait() returns immediately (without blocking for
        # the timeout) when the event is already set, so a large timeout
        # here is safe and still exercises the real stdlib primitive.
        event = threading.Event()
        event.set()
        strategy = nap.sleep_using_event(event)

        strategy(60)
