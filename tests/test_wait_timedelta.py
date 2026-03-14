import asyncio
import datetime
import functools
import unittest

from tenacity import Future
from tenacity import RetryError
from tenacity import Retrying
from tenacity import retry
from tenacity.asyncio import AsyncRetrying
from tenacity.stop import stop_after_attempt
from tenacity.stop import stop_before_delay
from tenacity.wait import wait_chain
from tenacity.wait import wait_combine
from tenacity.wait import wait_exception
from tenacity.wait import wait_none
from tenacity.wait import wait_base

try:
    from tornado import gen
    from tornado.ioloop import IOLoop
    from tenacity.tornadoweb import TornadoRetrying

    HAS_TORNADO = True
except ImportError:
    HAS_TORNADO = False


class _DummyState:
    def __init__(self, attempt_number=1):
        self.attempt_number = attempt_number
        self.outcome = None


def _failed_state(exc, attempt_number=1):
    state = _DummyState(attempt_number=attempt_number)
    fut = Future(attempt_number)
    fut.set_exception(exc)
    state.outcome = fut
    return state


def _successful_state(value, attempt_number=1):
    state = _DummyState(attempt_number=attempt_number)
    fut = Future(attempt_number)
    fut.set_result(value)
    state.outcome = fut
    return state


class _ConstWait(wait_base):
    def __init__(self, value):
        self.value = value

    def __call__(self, retry_state):
        return self.value


class _ByAttemptWait(wait_base):
    def __init__(self, values):
        self.values = values

    def __call__(self, retry_state):
        idx = min(retry_state.attempt_number - 1, len(self.values) - 1)
        return self.values[idx]


def asynctest(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop_policy().new_event_loop()
        try:
            return loop.run_until_complete(fn(*args, **kwargs))
        finally:
            loop.close()

    return wrapper


class TestWaitStrategyDirect(unittest.TestCase):
    def test_wait_combine_normalizes_timedelta_and_numeric(self):
        strategy = wait_combine(_ConstWait(datetime.timedelta(seconds=1.25)), _ConstWait(0.5))
        value = strategy(_DummyState())
        self.assertEqual(value, 1.75)
        self.assertIsInstance(value, float)

    def test_wait_combine_clamps_each_component_before_sum(self):
        strategy = wait_combine(
            _ConstWait(datetime.timedelta(seconds=2)),
            _ConstWait(datetime.timedelta(seconds=-3)),
            _ConstWait(-4),
            _ConstWait(0.25),
        )
        value = strategy(_DummyState())
        self.assertEqual(value, 2.25)

    def test_wait_combine_all_negative_clamps_to_zero(self):
        strategy = wait_combine(_ConstWait(-1), _ConstWait(datetime.timedelta(seconds=-2)))
        value = strategy(_DummyState())
        self.assertEqual(value, 0.0)

    def test_wait_combine_nested_strategy_keeps_normalized_float(self):
        nested = wait_combine(_ConstWait(datetime.timedelta(seconds=0.3)), _ConstWait(0.2))
        strategy = wait_combine(nested, _ConstWait(datetime.timedelta(seconds=0.5)))
        value = strategy(_DummyState())
        self.assertAlmostEqual(value, 1.0)
        self.assertIsInstance(value, float)

    def test_wait_chain_normalizes_selected_timedelta(self):
        strategy = wait_chain(_ConstWait(datetime.timedelta(seconds=1.5)), _ConstWait(2))
        value = strategy(_DummyState(attempt_number=1))
        self.assertEqual(value, 1.5)

    def test_wait_chain_clamps_negative_selected_value(self):
        strategy = wait_chain(_ConstWait(datetime.timedelta(seconds=-7)))
        value = strategy(_DummyState(attempt_number=1))
        self.assertEqual(value, 0.0)

    def test_wait_chain_uses_last_strategy_after_exhaustion(self):
        strategy = wait_chain(_ConstWait(0.1), _ConstWait(datetime.timedelta(seconds=0.2)))
        value = strategy(_DummyState(attempt_number=50))
        self.assertEqual(value, 0.2)

    def test_wait_chain_returns_float_type(self):
        strategy = wait_chain(_ConstWait(3))
        value = strategy(_DummyState(attempt_number=1))
        self.assertEqual(value, 3.0)
        self.assertIsInstance(value, float)

    def test_wait_exception_normalizes_timedelta_predicate(self):
        strategy = wait_exception(lambda exc: datetime.timedelta(seconds=0.75))
        value = strategy(_failed_state(ValueError("boom")))
        self.assertEqual(value, 0.75)

    def test_wait_exception_clamps_negative_predicate_value(self):
        strategy = wait_exception(lambda exc: datetime.timedelta(seconds=-4))
        value = strategy(_failed_state(ValueError("boom")))
        self.assertEqual(value, 0.0)

    def test_wait_exception_raises_before_outcome_is_set(self):
        strategy = wait_exception(lambda exc: 1)
        with self.assertRaises(RuntimeError):
            strategy(_DummyState())

    def test_wait_exception_raises_for_success_outcome(self):
        strategy = wait_exception(lambda exc: 1)
        with self.assertRaises(RuntimeError):
            strategy(_successful_state("ok"))

    def test_wait_exception_returns_float_type(self):
        strategy = wait_exception(lambda exc: 2)
        value = strategy(_failed_state(ValueError("boom")))
        self.assertEqual(value, 2.0)
        self.assertIsInstance(value, float)

    def test_wait_combine_three_components_keeps_normalized_behavior(self):
        strategy = wait_combine(
            _ConstWait(datetime.timedelta(seconds=0.4)),
            _ConstWait(-1),
            _ConstWait(0.6),
        )
        value = strategy(_DummyState())
        self.assertEqual(value, 1.0)


class TestWaitTimedeltaSync(unittest.TestCase):
    def test_wait_timedelta_converted_for_sleep_calls(self):
        sleep_calls = []
        attempts = {"n": 0}

        def sleep_fn(seconds):
            sleep_calls.append(seconds)

        r = Retrying(
            stop=stop_after_attempt(3),
            wait=lambda _: datetime.timedelta(seconds=1.25),
            sleep=sleep_fn,
        )

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(r(fn), "ok")
        self.assertEqual(sleep_calls, [1.25, 1.25])

    def test_wait_negative_timedelta_is_clamped_for_sleep_and_stats(self):
        sleep_calls = []
        attempts = {"n": 0}

        r = Retrying(
            stop=stop_after_attempt(3),
            wait=lambda _: datetime.timedelta(seconds=-5),
            sleep=lambda seconds: sleep_calls.append(seconds),
        )

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(r(fn), "ok")
        self.assertEqual(sleep_calls, [0.0, 0.0])
        self.assertEqual(r.statistics["idle_for"], 0.0)

    def test_wait_mixed_values_are_normalized_per_attempt(self):
        sleep_calls = []
        attempts = {"n": 0}
        values = [datetime.timedelta(seconds=0.75), -2, datetime.timedelta(seconds=1.5)]

        def wait_fn(state):
            return values[state.attempt_number - 1]

        r = Retrying(stop=stop_after_attempt(4), wait=wait_fn, sleep=lambda x: sleep_calls.append(x))

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 4:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(r(fn), "ok")
        self.assertEqual(sleep_calls, [0.75, 0.0, 1.5])
        self.assertAlmostEqual(r.statistics["idle_for"], 2.25)

    def test_stop_before_delay_uses_normalized_wait(self):
        attempts = {"n": 0}

        r = Retrying(
            stop=stop_before_delay(1),
            wait=lambda _: datetime.timedelta(seconds=10),
            sleep=lambda _: None,
        )

        def fn():
            attempts["n"] += 1
            raise RuntimeError("always fail")

        with self.assertRaises(RetryError):
            r(fn)
        self.assertEqual(attempts["n"], 1)

    def test_retry_with_wait_timedelta_override(self):
        sleep_calls = []
        attempts = {"n": 0}

        @retry(stop=stop_after_attempt(3), wait=wait_none())
        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        overridden = fn.retry_with(
            wait=lambda _: datetime.timedelta(seconds=1.5),
            sleep=lambda seconds: sleep_calls.append(seconds),
        )

        self.assertEqual(overridden(), "ok")
        self.assertEqual(sleep_calls, [1.5, 1.5])

    def test_copy_wait_negative_override_is_clamped(self):
        sleep_calls = []
        attempts = {"n": 0}

        base = Retrying(stop=stop_after_attempt(3), wait=wait_none(), sleep=lambda x: sleep_calls.append(x))
        overridden = base.copy(wait=lambda _: datetime.timedelta(seconds=-1))

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(overridden(fn), "ok")
        self.assertEqual(sleep_calls, [0.0, 0.0])

    def test_manual_iteration_uses_normalized_wait(self):
        sleep_calls = []
        attempts = 0

        r = Retrying(
            stop=stop_after_attempt(3),
            wait=lambda _: datetime.timedelta(seconds=0.5),
            sleep=lambda seconds: sleep_calls.append(seconds),
        )

        for attempt in r:
            with attempt:
                attempts += 1
                if attempts < 3:
                    raise ValueError("retry")

        self.assertEqual(sleep_calls, [0.5, 0.5])

    def test_wait_combine_strategy_in_retry_normalizes_and_clamps(self):
        sleep_calls = []
        attempts = {"n": 0}

        strategy = wait_combine(
            _ConstWait(datetime.timedelta(seconds=1)),
            _ConstWait(datetime.timedelta(seconds=-2)),
            _ConstWait(0.25),
        )
        r = Retrying(stop=stop_after_attempt(3), wait=strategy, sleep=lambda x: sleep_calls.append(x))

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(r(fn), "ok")
        self.assertEqual(sleep_calls, [1.25, 1.25])

    def test_wait_chain_strategy_in_retry_normalizes(self):
        sleep_calls = []
        attempts = {"n": 0}

        strategy = wait_chain(
            _ConstWait(datetime.timedelta(seconds=0.3)),
            _ConstWait(datetime.timedelta(seconds=-9)),
            _ConstWait(0.8),
        )
        r = Retrying(stop=stop_after_attempt(4), wait=strategy, sleep=lambda x: sleep_calls.append(x))

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 4:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(r(fn), "ok")
        self.assertEqual(sleep_calls, [0.3, 0.0, 0.8])

    def test_wait_exception_strategy_in_retry_normalizes(self):
        sleep_calls = []
        attempts = {"n": 0}
        strategy = wait_exception(lambda exc: datetime.timedelta(seconds=0.6))

        r = Retrying(stop=stop_after_attempt(3), wait=strategy, sleep=lambda x: sleep_calls.append(x))

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(r(fn), "ok")
        self.assertEqual(sleep_calls, [0.6, 0.6])


class TestWaitTimedeltaAsync(unittest.TestCase):
    @asynctest
    async def test_async_wait_timedelta_converted_for_sleep_calls(self):
        sleep_calls = []
        attempts = {"n": 0}

        async def wait_fn(_):
            return datetime.timedelta(seconds=0.25)

        async def sleep_fn(seconds):
            sleep_calls.append(seconds)

        r = AsyncRetrying(stop=stop_after_attempt(3), wait=wait_fn, sleep=sleep_fn)

        async def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(await r(fn), "ok")
        self.assertEqual(sleep_calls, [0.25, 0.25])

    @asynctest
    async def test_async_sync_wait_timedelta_callable_is_converted(self):
        sleep_calls = []
        attempts = {"n": 0}

        def wait_fn(_):
            return datetime.timedelta(seconds=0.75)

        async def sleep_fn(seconds):
            sleep_calls.append(seconds)

        r = AsyncRetrying(stop=stop_after_attempt(3), wait=wait_fn, sleep=sleep_fn)

        async def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(await r(fn), "ok")
        self.assertEqual(sleep_calls, [0.75, 0.75])

    @asynctest
    async def test_async_negative_wait_is_clamped(self):
        sleep_calls = []
        attempts = {"n": 0}

        async def wait_fn(_):
            return datetime.timedelta(seconds=-3)

        async def sleep_fn(seconds):
            sleep_calls.append(seconds)

        r = AsyncRetrying(stop=stop_after_attempt(3), wait=wait_fn, sleep=sleep_fn)

        async def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(await r(fn), "ok")
        self.assertEqual(sleep_calls, [0.0, 0.0])
        self.assertEqual(r.statistics["idle_for"], 0.0)

    @asynctest
    async def test_async_retry_with_wait_timedelta_override(self):
        sleep_calls = []
        attempts = {"n": 0}

        async def sleep_fn(seconds):
            sleep_calls.append(seconds)

        @retry(stop=stop_after_attempt(3), wait=wait_none())
        async def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        overridden = fn.retry_with(wait=lambda _: datetime.timedelta(seconds=0.6), sleep=sleep_fn)

        self.assertEqual(await overridden(), "ok")
        self.assertEqual(sleep_calls, [0.6, 0.6])

    @asynctest
    async def test_async_iterator_path_uses_normalized_wait(self):
        sleep_calls = []
        attempts = 0

        async def wait_fn(_):
            return datetime.timedelta(seconds=0.5)

        async def sleep_fn(seconds):
            sleep_calls.append(seconds)

        r = AsyncRetrying(stop=stop_after_attempt(3), wait=wait_fn, sleep=sleep_fn)

        async for attempt in r:
            with attempt:
                attempts += 1
                if attempts < 3:
                    raise ValueError("retry")

        self.assertEqual(sleep_calls, [0.5, 0.5])

    @asynctest
    async def test_async_stop_before_delay_uses_normalized_wait(self):
        attempts = {"n": 0}

        async def wait_fn(_):
            return datetime.timedelta(seconds=5)

        async def sleep_fn(_):
            return None

        r = AsyncRetrying(stop=stop_before_delay(1), wait=wait_fn, sleep=sleep_fn)

        async def fn():
            attempts["n"] += 1
            raise RuntimeError("always fail")

        with self.assertRaises(RetryError):
            await r(fn)
        self.assertEqual(attempts["n"], 1)

    @asynctest
    async def test_async_wait_combine_strategy_in_retry(self):
        sleep_calls = []
        attempts = {"n": 0}
        strategy = wait_combine(_ConstWait(datetime.timedelta(seconds=0.2)), _ConstWait(-3), _ConstWait(0.4))

        async def sleep_fn(seconds):
            sleep_calls.append(seconds)

        r = AsyncRetrying(stop=stop_after_attempt(3), wait=strategy, sleep=sleep_fn)

        async def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(await r(fn), "ok")
        self.assertEqual(len(sleep_calls), 2)
        self.assertAlmostEqual(sleep_calls[0], 0.6)
        self.assertAlmostEqual(sleep_calls[1], 0.6)

    @asynctest
    async def test_async_wait_chain_strategy_in_retry(self):
        sleep_calls = []
        attempts = {"n": 0}
        strategy = wait_chain(_ConstWait(datetime.timedelta(seconds=0.3)), _ConstWait(datetime.timedelta(seconds=-2)))

        async def sleep_fn(seconds):
            sleep_calls.append(seconds)

        r = AsyncRetrying(stop=stop_after_attempt(3), wait=strategy, sleep=sleep_fn)

        async def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(await r(fn), "ok")
        self.assertEqual(sleep_calls, [0.3, 0.0])

    @asynctest
    async def test_async_wait_exception_strategy_in_retry(self):
        sleep_calls = []
        attempts = {"n": 0}
        strategy = wait_exception(lambda exc: datetime.timedelta(seconds=-1))

        async def sleep_fn(seconds):
            sleep_calls.append(seconds)

        r = AsyncRetrying(stop=stop_after_attempt(3), wait=strategy, sleep=sleep_fn)

        async def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            return "ok"

        self.assertEqual(await r(fn), "ok")
        self.assertEqual(sleep_calls, [0.0, 0.0])


@unittest.skipUnless(HAS_TORNADO, "tornado is required")
class TestWaitTimedeltaTornado(unittest.TestCase):
    def _run(self, fn):
        io_loop = IOLoop()
        try:
            return io_loop.run_sync(fn)
        finally:
            io_loop.close(all_fds=True)

    def test_tornado_wait_timedelta_converted_for_sleep_calls(self):
        attempts = {"n": 0}
        sleep_calls = []

        def wait_fn(_):
            return datetime.timedelta(seconds=1.5)

        @gen.coroutine
        def sleep_fn(seconds):
            sleep_calls.append(seconds)
            raise gen.Return(None)

        @gen.coroutine
        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            raise gen.Return("ok")

        def run():
            r = TornadoRetrying(stop=stop_after_attempt(3), wait=wait_fn, sleep=sleep_fn)
            return r(fn)

        self.assertEqual(self._run(run), "ok")
        self.assertEqual(sleep_calls, [1.5, 1.5])

    def test_tornado_negative_wait_is_clamped(self):
        attempts = {"n": 0}
        sleep_calls = []

        def wait_fn(_):
            return datetime.timedelta(seconds=-4)

        @gen.coroutine
        def sleep_fn(seconds):
            sleep_calls.append(seconds)
            raise gen.Return(None)

        @gen.coroutine
        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            raise gen.Return("ok")

        def run():
            r = TornadoRetrying(stop=stop_after_attempt(3), wait=wait_fn, sleep=sleep_fn)
            return r(fn), r

        result, retrying_obj = self._run(run)
        self.assertEqual(result, "ok")
        self.assertEqual(sleep_calls, [0.0, 0.0])
        self.assertEqual(retrying_obj.statistics["idle_for"], 0.0)

    def test_tornado_wait_combine_strategy_in_retry(self):
        attempts = {"n": 0}
        sleep_calls = []
        strategy = wait_combine(_ConstWait(datetime.timedelta(seconds=0.4)), _ConstWait(-8), _ConstWait(0.1))

        @gen.coroutine
        def sleep_fn(seconds):
            sleep_calls.append(seconds)
            raise gen.Return(None)

        @gen.coroutine
        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            raise gen.Return("ok")

        def run():
            r = TornadoRetrying(stop=stop_after_attempt(3), wait=strategy, sleep=sleep_fn)
            return r(fn)

        self.assertEqual(self._run(run), "ok")
        self.assertEqual(sleep_calls, [0.5, 0.5])

    def test_tornado_wait_chain_strategy_in_retry(self):
        attempts = {"n": 0}
        sleep_calls = []
        strategy = wait_chain(_ConstWait(datetime.timedelta(seconds=0.2)), _ConstWait(datetime.timedelta(seconds=-9)))

        @gen.coroutine
        def sleep_fn(seconds):
            sleep_calls.append(seconds)
            raise gen.Return(None)

        @gen.coroutine
        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            raise gen.Return("ok")

        def run():
            r = TornadoRetrying(stop=stop_after_attempt(3), wait=strategy, sleep=sleep_fn)
            return r(fn)

        self.assertEqual(self._run(run), "ok")
        self.assertEqual(sleep_calls, [0.2, 0.0])

    def test_tornado_wait_exception_strategy_in_retry(self):
        attempts = {"n": 0}
        sleep_calls = []
        strategy = wait_exception(lambda exc: datetime.timedelta(seconds=-1))

        @gen.coroutine
        def sleep_fn(seconds):
            sleep_calls.append(seconds)
            raise gen.Return(None)

        @gen.coroutine
        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            raise gen.Return("ok")

        def run():
            r = TornadoRetrying(stop=stop_after_attempt(3), wait=strategy, sleep=sleep_fn)
            return r(fn)

        self.assertEqual(self._run(run), "ok")
        self.assertEqual(sleep_calls, [0.0, 0.0])

    def test_tornado_stop_before_delay_uses_normalized_wait(self):
        attempts = {"n": 0}

        def wait_fn(_):
            return datetime.timedelta(seconds=20)

        @gen.coroutine
        def sleep_fn(_):
            raise gen.Return(None)

        @gen.coroutine
        def fn():
            attempts["n"] += 1
            raise ValueError("always fail")

        def run():
            r = TornadoRetrying(stop=stop_before_delay(1), wait=wait_fn, sleep=sleep_fn)
            return r(fn)

        with self.assertRaises(RetryError):
            self._run(run)
        self.assertEqual(attempts["n"], 1)

    def test_tornado_copy_wait_timedelta_override(self):
        attempts = {"n": 0}
        sleep_calls = []

        @gen.coroutine
        def sleep_fn(seconds):
            sleep_calls.append(seconds)
            raise gen.Return(None)

        @gen.coroutine
        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            raise gen.Return("ok")

        def run():
            base = TornadoRetrying(stop=stop_after_attempt(3), wait=wait_none(), sleep=sleep_fn)
            overridden = base.copy(wait=lambda _: datetime.timedelta(seconds=0.8))
            return overridden(fn)

        self.assertEqual(self._run(run), "ok")
        self.assertEqual(sleep_calls, [0.8, 0.8])

    def test_tornado_wait_numeric_still_works(self):
        attempts = {"n": 0}
        sleep_calls = []

        @gen.coroutine
        def sleep_fn(seconds):
            sleep_calls.append(seconds)
            raise gen.Return(None)

        @gen.coroutine
        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("retry")
            raise gen.Return("ok")

        def run():
            r = TornadoRetrying(stop=stop_after_attempt(3), wait=lambda _: 2, sleep=sleep_fn)
            return r(fn)

        self.assertEqual(self._run(run), "ok")
        self.assertEqual(sleep_calls, [2.0, 2.0])


if __name__ == "__main__":
    unittest.main()
