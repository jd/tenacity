"""Tests for after return value overriding sleep duration."""
import asyncio
import unittest

import tenacity
from tenacity import (
    RetryCallState,
    Retrying,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
    wait_none,
)

try:
    from tenacity import tornadoweb
    from tornado import concurrent
    from tornado import gen
    from tornado import ioloop
except ImportError:
    HAS_TORNADO = False
else:
    HAS_TORNADO = True


class TestAfterOverrideSyncBasic(unittest.TestCase):
    """after return value overrides sleep duration in sync."""

    def test_none_return_keeps_original_sleep(self):
        sleeps = []

        def my_after(retry_state):
            return None  # No override

        def record_sleep(seconds):
            sleeps.append(seconds)

        call_count = 0

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_fixed(5),
            after=my_after,
            sleep=record_sleep,
            reraise=True,
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("retry")
            return "ok"

        fn()
        # Sleep should be 5.0 (original), not overridden
        self.assertEqual(sleeps, [5.0, 5.0])

    def test_float_return_overrides_sleep(self):
        sleeps = []

        def my_after(retry_state):
            return 1.0  # Override to 1 second

        def record_sleep(seconds):
            sleeps.append(seconds)

        call_count = 0

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_fixed(5),
            after=my_after,
            sleep=record_sleep,
            reraise=True,
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("retry")
            return "ok"

        fn()
        # Sleep should be overridden to 1.0
        self.assertEqual(sleeps, [1.0, 1.0])

    def test_zero_return_overrides_to_zero(self):
        sleeps = []

        def my_after(retry_state):
            return 0.0

        def record_sleep(seconds):
            sleeps.append(seconds)

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(10),
            after=my_after,
            sleep=record_sleep,
            reraise=True,
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        fn()
        self.assertEqual(sleeps, [0.0])

    def test_negative_return_clamped_to_zero(self):
        sleeps = []

        def my_after(retry_state):
            return -5.0  # Negative should be clamped to 0

        def record_sleep(seconds):
            sleeps.append(seconds)

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(10),
            after=my_after,
            sleep=record_sleep,
            reraise=True,
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        fn()
        self.assertEqual(sleeps, [0.0])

    def test_int_return_overrides_sleep(self):
        sleeps = []

        def my_after(retry_state):
            return 3

        def record_sleep(seconds):
            sleeps.append(seconds)

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(10),
            after=my_after,
            sleep=record_sleep,
            reraise=True,
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        fn()
        self.assertEqual(sleeps, [3.0])
        self.assertIsInstance(sleeps[0], float)


class TestAfterOverrideIdleFor(unittest.TestCase):
    """idle_for statistics tracks the overridden delay value."""

    def test_idle_for_tracks_overridden_value(self):
        def my_after(retry_state):
            return 2.0  # Override from 10 to 2

        call_count = 0

        @retry(
            stop=stop_after_attempt(4),
            wait=wait_fixed(10),
            after=my_after,
            sleep=lambda x: None,  # no-op sleep
            reraise=True,
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise ValueError("retry")
            return "ok"

        result = fn()
        self.assertEqual(result, "ok")
        # idle_for should track overridden sleep (2.0 * 3 retries = 6.0)
        self.assertEqual(fn.statistics["idle_for"], 6.0)

    def test_idle_for_with_no_override(self):
        def my_after(retry_state):
            return None  # No override

        call_count = 0

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_fixed(5),
            after=my_after,
            sleep=lambda x: None,
            reraise=True,
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("retry")
            return "ok"

        fn()
        # idle_for should track original (5.0 * 2 = 10.0)
        self.assertEqual(fn.statistics["idle_for"], 10.0)

    def test_idle_for_mixed_overrides(self):
        """Some retries override, some don't."""
        call_count = 0

        def my_after(retry_state):
            # Override only on first retry
            if retry_state.attempt_number == 1:
                return 1.0
            return None

        @retry(
            stop=stop_after_attempt(4),
            wait=wait_fixed(5),
            after=my_after,
            sleep=lambda x: None,
            reraise=True,
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise ValueError("retry")
            return "ok"

        fn()
        # Attempt 1 fails -> after returns 1.0 (override)
        # Attempt 2 fails -> after returns None (keep 5.0)
        # Attempt 3 fails -> after returns None (keep 5.0)
        # Attempt 4 succeeds
        self.assertEqual(fn.statistics["idle_for"], 1.0 + 5.0 + 5.0)


class TestAfterOverrideSleepAction(unittest.TestCase):
    """Sleep action receives the overridden delay value."""

    def test_sleep_receives_overridden_value(self):
        captured = []

        def my_after(retry_state):
            return 2.0

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(10),
            after=my_after,
            sleep=lambda x: captured.append(x),
            reraise=True,
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        fn()
        self.assertEqual(captured, [2.0])


class TestAfterOverrideNoAfter(unittest.TestCase):
    """When after is None, behavior is unchanged."""

    def test_no_after_original_sleep(self):
        sleeps = []

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(5),
            after=None,
            sleep=lambda x: sleeps.append(x),
            reraise=True,
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        fn()
        self.assertEqual(sleeps, [5.0])


class TestAfterOverrideBackwardCompat(unittest.TestCase):
    """Existing after callbacks that return None still work."""

    def test_existing_callback_returning_none_implicitly(self):
        sleeps = []
        callback_called = []

        def my_after(retry_state):
            callback_called.append(True)
            # Implicit None return

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(5),
            after=my_after,
            sleep=lambda x: sleeps.append(x),
            reraise=True,
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        fn()
        self.assertTrue(callback_called)
        self.assertEqual(sleeps, [5.0])


def _make_async_sleep_recorder(sleeps_list):
    """Create an async sleep function that records durations."""
    async def async_sleep(seconds):
        sleeps_list.append(seconds)
    return async_sleep


class TestAfterOverrideAsync(unittest.TestCase):
    """Override works with async retrying."""

    def test_async_sync_callback_override(self):
        sleeps = []

        def my_after(retry_state):
            return 1.0

        call_count = 0

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_fixed(10),
            after=my_after,
            sleep=_make_async_sleep_recorder(sleeps),
            reraise=True,
        )
        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("retry")
            return "ok"

        asyncio.run(fn())
        self.assertEqual(sleeps, [1.0, 1.0])

    def test_async_callback_override(self):
        sleeps = []

        async def my_after(retry_state):
            return 2.0

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(10),
            after=my_after,
            sleep=_make_async_sleep_recorder(sleeps),
            reraise=True,
        )
        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        asyncio.run(fn())
        self.assertEqual(sleeps, [2.0])

    def test_async_callback_none_no_override(self):
        sleeps = []

        async def my_after(retry_state):
            return None

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(5),
            after=my_after,
            sleep=_make_async_sleep_recorder(sleeps),
            reraise=True,
        )
        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        asyncio.run(fn())
        self.assertEqual(sleeps, [5.0])

    def test_async_negative_override_clamped_to_zero(self):
        sleeps = []

        async def my_after(retry_state):
            return -7.0

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(5),
            after=my_after,
            sleep=_make_async_sleep_recorder(sleeps),
            reraise=True,
        )
        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        asyncio.run(fn())
        self.assertEqual(sleeps, [0.0])

    def test_async_sync_callback_returning_awaitable_override(self):
        sleeps = []

        async def override_value():
            return 1.25

        def my_after(retry_state):
            return override_value()

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(10),
            after=my_after,
            sleep=_make_async_sleep_recorder(sleeps),
            reraise=True,
        )
        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        asyncio.run(fn())
        self.assertEqual(sleeps, [1.25])

    def test_async_callback_returning_nested_awaitable_override(self):
        sleeps = []

        async def nested_override_value():
            async def final_value():
                return 0.75

            return final_value()

        async def my_after(retry_state):
            return nested_override_value()

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(10),
            after=my_after,
            sleep=_make_async_sleep_recorder(sleeps),
            reraise=True,
        )
        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        asyncio.run(fn())
        self.assertEqual(sleeps, [0.75])

    def test_async_nested_awaitable_resolving_none_keeps_original_sleep(self):
        sleeps = []

        async def nested_none():
            async def final_none():
                return None

            return final_none()

        def my_after(retry_state):
            return nested_none()

        call_count = 0

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(4),
            after=my_after,
            sleep=_make_async_sleep_recorder(sleeps),
            reraise=True,
        )
        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            return "ok"

        asyncio.run(fn())
        self.assertEqual(sleeps, [4.0])

    def test_async_idle_for_tracks_override(self):
        async def my_after(retry_state):
            return 1.0

        call_count = 0

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_fixed(10),
            after=my_after,
            sleep=_make_async_sleep_recorder([]),
            reraise=True,
        )
        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("retry")
            return "ok"

        asyncio.run(fn())
        self.assertEqual(fn.statistics["idle_for"], 2.0)  # 1.0 * 2 retries


@unittest.skipUnless(HAS_TORNADO, "tornado is not installed")
class TestAfterOverrideTornado(unittest.TestCase):
    """Override works with tornado retrying, including awaitable returns."""

    def _run_sync(self, callback):
        loop = ioloop.IOLoop()
        try:
            return loop.run_sync(callback)
        finally:
            loop.close()

    def test_tornado_sync_callback_returning_future_override(self):
        sleeps = []

        def my_after(retry_state):
            future = concurrent.Future()
            future.set_result(1.5)
            return future

        def record_sleep(seconds):
            sleeps.append(seconds)
            future = concurrent.Future()
            future.set_result(None)
            return future

        retrying = tornadoweb.TornadoRetrying(
            stop=stop_after_attempt(2),
            wait=wait_fixed(10),
            retry=retry_if_exception_type(ValueError),
            after=my_after,
            sleep=record_sleep,
            reraise=True,
        )

        call_count = 0

        @gen.coroutine
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            raise gen.Return("ok")

        result = self._run_sync(lambda: retrying(fn))
        self.assertEqual(result, "ok")
        self.assertEqual(sleeps, [1.5])

    def test_tornado_negative_override_clamped_to_zero(self):
        sleeps = []

        def my_after(retry_state):
            future = concurrent.Future()
            future.set_result(-9.0)
            return future

        def record_sleep(seconds):
            sleeps.append(seconds)
            future = concurrent.Future()
            future.set_result(None)
            return future

        retrying = tornadoweb.TornadoRetrying(
            stop=stop_after_attempt(2),
            wait=wait_fixed(10),
            retry=retry_if_exception_type(ValueError),
            after=my_after,
            sleep=record_sleep,
            reraise=True,
        )

        call_count = 0

        @gen.coroutine
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            raise gen.Return("ok")

        result = self._run_sync(lambda: retrying(fn))
        self.assertEqual(result, "ok")
        self.assertEqual(sleeps, [0.0])

    def test_tornado_callback_returning_nested_awaitable_override(self):
        sleeps = []

        @gen.coroutine
        def nested_override():
            future = concurrent.Future()
            future.set_result(0.25)
            raise gen.Return(future)

        @gen.coroutine
        def my_after(retry_state):
            raise gen.Return(nested_override())

        def record_sleep(seconds):
            sleeps.append(seconds)
            future = concurrent.Future()
            future.set_result(None)
            return future

        retrying = tornadoweb.TornadoRetrying(
            stop=stop_after_attempt(2),
            wait=wait_fixed(10),
            retry=retry_if_exception_type(ValueError),
            after=my_after,
            sleep=record_sleep,
            reraise=True,
        )

        call_count = 0

        @gen.coroutine
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            raise gen.Return("ok")

        result = self._run_sync(lambda: retrying(fn))
        self.assertEqual(result, "ok")
        self.assertEqual(sleeps, [0.25])

    def test_tornado_nested_awaitable_none_keeps_original_sleep(self):
        sleeps = []

        @gen.coroutine
        def nested_none():
            future = concurrent.Future()
            future.set_result(None)
            raise gen.Return(future)

        def my_after(retry_state):
            return nested_none()

        def record_sleep(seconds):
            sleeps.append(seconds)
            future = concurrent.Future()
            future.set_result(None)
            return future

        retrying = tornadoweb.TornadoRetrying(
            stop=stop_after_attempt(2),
            wait=wait_fixed(3),
            retry=retry_if_exception_type(ValueError),
            after=my_after,
            sleep=record_sleep,
            reraise=True,
        )

        call_count = 0

        @gen.coroutine
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry")
            raise gen.Return("ok")

        result = self._run_sync(lambda: retrying(fn))
        self.assertEqual(result, "ok")
        self.assertEqual(sleeps, [3.0])


class TestAfterOverrideSyncEdgeCases(unittest.TestCase):
    def test_false_return_overrides_to_zero(self):
        sleeps = []

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_fixed(9),
            after=lambda _: False,
            sleep=lambda x: sleeps.append(x),
            reraise=True,
        )
        def fn():
            raise ValueError("retry")

        with self.assertRaises(ValueError):
            fn()
        self.assertEqual(sleeps, [0.0])

    def test_after_receives_attempt_numbers_for_retries(self):
        seen = []
        calls = {"n": 0}

        @retry(stop=stop_after_attempt(4), wait=wait_fixed(1), after=lambda rs: seen.append(rs.attempt_number), sleep=lambda _: None, reraise=True)
        def fn():
            calls["n"] += 1
            if calls["n"] < 4:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(fn(), "ok")
        self.assertEqual(seen, [1, 2, 3])

    def test_wait_none_with_override_uses_after_value(self):
        sleeps = []
        calls = {"n": 0}

        @retry(stop=stop_after_attempt(3), wait=wait_none(), after=lambda _: 1.75, sleep=lambda x: sleeps.append(x), reraise=True)
        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(fn(), "ok")
        self.assertEqual(sleeps, [1.75, 1.75])


class TestAfterOverrideAsyncEdgeCases(unittest.TestCase):
    def test_async_false_return_overrides_to_zero(self):
        sleeps = []
        calls = {"n": 0}

        @retry(stop=stop_after_attempt(2), wait=wait_fixed(6), after=lambda _: False, sleep=_make_async_sleep_recorder(sleeps), reraise=True)
        async def fn():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(asyncio.run(fn()), "ok")
        self.assertEqual(sleeps, [0.0])

    def test_async_after_attempt_numbers(self):
        seen = []
        calls = {"n": 0}

        @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), after=lambda rs: seen.append(rs.attempt_number), sleep=_make_async_sleep_recorder([]), reraise=True)
        async def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(asyncio.run(fn()), "ok")
        self.assertEqual(seen, [1, 2])

    def test_async_double_nested_awaitable_override(self):
        sleeps = []
        calls = {"n": 0}

        async def lvl3():
            return 0.5

        async def lvl2():
            return lvl3()

        async def lvl1(_):
            return lvl2()

        @retry(stop=stop_after_attempt(2), wait=wait_fixed(9), after=lvl1, sleep=_make_async_sleep_recorder(sleeps), reraise=True)
        async def fn():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(asyncio.run(fn()), "ok")
        self.assertEqual(sleeps, [0.5])


@unittest.skipUnless(HAS_TORNADO, "tornado is not installed")
class TestAfterOverrideTornadoEdgeCases(unittest.TestCase):
    def _run_sync(self, callback):
        loop = ioloop.IOLoop()
        try:
            return loop.run_sync(callback)
        finally:
            loop.close()

    def test_tornado_none_keeps_original_sleep(self):
        sleeps = []
        calls = {"n": 0}

        def after_cb(_):
            future = concurrent.Future()
            future.set_result(None)
            return future

        def record_sleep(seconds):
            sleeps.append(seconds)
            future = concurrent.Future()
            future.set_result(None)
            return future

        retrying = tornadoweb.TornadoRetrying(stop=stop_after_attempt(2), wait=wait_fixed(4), retry=retry_if_exception_type(ValueError), after=after_cb, sleep=record_sleep, reraise=True)

        @gen.coroutine
        def fn():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("retry")
            raise gen.Return("ok")

        self.assertEqual(self._run_sync(lambda: retrying(fn)), "ok")
        self.assertEqual(sleeps, [4.0])

    def test_tornado_false_overrides_to_zero(self):
        sleeps = []
        calls = {"n": 0}

        def after_cb(_):
            future = concurrent.Future()
            future.set_result(False)
            return future

        def record_sleep(seconds):
            sleeps.append(seconds)
            future = concurrent.Future()
            future.set_result(None)
            return future

        retrying = tornadoweb.TornadoRetrying(stop=stop_after_attempt(2), wait=wait_fixed(4), retry=retry_if_exception_type(ValueError), after=after_cb, sleep=record_sleep, reraise=True)

        @gen.coroutine
        def fn():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("retry")
            raise gen.Return("ok")

        self.assertEqual(self._run_sync(lambda: retrying(fn)), "ok")
        self.assertEqual(sleeps, [0.0])

    def test_tornado_idle_for_tracks_override(self):
        calls = {"n": 0}

        def after_cb(_):
            future = concurrent.Future()
            future.set_result(1.25)
            return future

        def record_sleep(_):
            future = concurrent.Future()
            future.set_result(None)
            return future

        retrying = tornadoweb.TornadoRetrying(stop=stop_after_attempt(3), wait=wait_fixed(6), retry=retry_if_exception_type(ValueError), after=after_cb, sleep=record_sleep, reraise=True)

        @gen.coroutine
        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("retry")
            raise gen.Return("ok")

        self.assertEqual(self._run_sync(lambda: retrying(fn)), "ok")
        self.assertEqual(retrying.statistics["idle_for"], 2.5)


class TestAfterOverrideManualIteration(unittest.TestCase):
    """Override works with manual sync iteration."""

    def test_manual_iteration_override(self):
        sleeps = []

        def my_after(retry_state):
            return 0.5

        r = Retrying(
            stop=stop_after_attempt(3),
            wait=wait_fixed(10),
            after=my_after,
            sleep=lambda x: sleeps.append(x),
        )

        for attempt in r:
            with attempt:
                if r.statistics.get("attempt_number", 1) < 3:
                    raise ValueError("retry")

        self.assertEqual(sleeps, [0.5, 0.5])

    def test_manual_iteration_none_keeps_original(self):
        sleeps = []

        r = Retrying(stop=stop_after_attempt(3), wait=wait_fixed(2), after=lambda _: None, sleep=lambda x: sleeps.append(x))

        for attempt in r:
            with attempt:
                if r.statistics.get("attempt_number", 1) < 3:
                    raise ValueError("retry")

        self.assertEqual(sleeps, [2.0, 2.0])

    def test_manual_iteration_negative_clamps(self):
        sleeps = []

        r = Retrying(stop=stop_after_attempt(2), wait=wait_fixed(3), after=lambda _: -10, sleep=lambda x: sleeps.append(x))

        for attempt in r:
            with attempt:
                if r.statistics.get("attempt_number", 1) < 2:
                    raise ValueError("retry")

        self.assertEqual(sleeps, [0.0])


if __name__ == "__main__":
    unittest.main()
