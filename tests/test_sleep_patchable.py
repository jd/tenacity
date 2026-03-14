import asyncio
import functools
import unittest

import tenacity
from tenacity import RetryError
from tenacity import Retrying
from tenacity import retry
from tenacity.asyncio import AsyncRetrying
from tenacity.stop import stop_after_attempt
from tenacity.wait import wait_fixed
from tenacity.wait import wait_none

try:
    from tornado import gen
    from tornado.ioloop import IOLoop
    from tenacity.tornadoweb import TornadoRetrying

    HAS_TORNADO = True
except ImportError:
    HAS_TORNADO = False


def asynctest(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop_policy().new_event_loop()
        try:
            return loop.run_until_complete(fn(*args, **kwargs))
        finally:
            loop.close()

    return wrapper


class C1:
    def __init__(self):
        self.v = []

    def __call__(self, x):
        self.v.append(float(x))


class C2:
    def __init__(self):
        self.v = []

    async def __call__(self, x):
        self.v.append(float(x))


def a1(v1, t1, value=None, error=None):
    async def f1():
        v1.append(t1)
        if error is not None:
            raise error
        return value

    async def f2():
        return f1()

    return f2()


if HAS_TORNADO:

    def t1(v1, t2, value=None, error=None):
        @gen.coroutine
        def f1():
            v1.append(t2)
            if error is not None:
                raise error
            raise gen.Return(value)

        @gen.coroutine
        def f2():
            raise gen.Return(f1())

        return f2()


class TestA(unittest.TestCase):
    def setUp(self):
        self._old_sleep = tenacity.nap.sleep

    def tearDown(self):
        tenacity.nap.sleep = self._old_sleep

    @staticmethod
    def _fail():
        raise ValueError("x")

    def test_behavior_1(self):
        c1 = C1()
        c2 = C1()

        tenacity.nap.sleep = c1
        r1 = Retrying(wait=wait_fixed(1), stop=stop_after_attempt(3))

        tenacity.nap.sleep = c2
        r2 = Retrying(wait=wait_fixed(1), stop=stop_after_attempt(3))

        with self.assertRaises(RetryError):
            r1(self._fail)
        with self.assertRaises(RetryError):
            r2(self._fail)

        self.assertEqual(c1.v, [1.0, 1.0])
        self.assertEqual(c2.v, [1.0, 1.0])

    def test_behavior_2(self):
        c1 = C1()
        c2 = C1()

        tenacity.nap.sleep = c1
        r1 = Retrying(sleep=c2, wait=wait_fixed(2), stop=stop_after_attempt(3))

        with self.assertRaises(RetryError):
            r1(self._fail)

        self.assertEqual(c1.v, [])
        self.assertEqual(c2.v, [2.0, 2.0])

    def test_behavior_3(self):
        c1 = C1()
        c2 = C1()

        tenacity.nap.sleep = c1

        @retry(wait=wait_fixed(3), stop=stop_after_attempt(3))
        def f1():
            raise ValueError("y")

        r1 = f1.retry.copy()
        f2 = f1.retry_with(stop=stop_after_attempt(3))

        tenacity.nap.sleep = c2

        with self.assertRaises(RetryError):
            r1(self._fail)
        with self.assertRaises(RetryError):
            f2()

        self.assertEqual(c1.v, [3.0, 3.0, 3.0, 3.0])
        self.assertEqual(c2.v, [])

    def test_behavior_4(self):
        v1 = []
        v2 = []

        def f1(s1):
            v1.append(s1.attempt_number)
            return 4

        def f2(s1):
            v2.append(s1.attempt_number)

        r1 = Retrying(
            sleep=None,
            wait=f1,
            stop=stop_after_attempt(4),
            before_sleep=f2,
        )
        n1 = {"v": 0}

        def f3():
            n1["v"] += 1
            if n1["v"] < 4:
                raise ValueError("z")
            return "ok"

        out = r1(f3)
        self.assertEqual(out, "ok")
        self.assertEqual(n1["v"], 4)
        self.assertEqual(v1, [1, 2, 3])
        self.assertEqual(v2, [])
        self.assertAlmostEqual(r1.statistics["idle_for"], 12.0, places=5)

    def test_behavior_5(self):
        c1 = C1()

        v1 = []

        def f1(s1):
            v1.append(s1.attempt_number)

        r1 = Retrying(
            sleep=c1,
            wait=wait_fixed(2),
            stop=stop_after_attempt(3),
            before_sleep=f1,
        )
        r2 = r1.copy(sleep=None)
        n1 = {"v": 0}

        def f2():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            return "ok"

        out1 = r2(f2)
        self.assertEqual(out1, "ok")
        self.assertEqual(c1.v, [])
        self.assertEqual(v1, [])
        self.assertAlmostEqual(r2.statistics["idle_for"], 4.0, places=5)

        v2 = []

        def f3(s1):
            v2.append(s1.attempt_number)

        n2 = {"v": 0}

        @retry(
            sleep=c1,
            wait=wait_fixed(2),
            stop=stop_after_attempt(3),
            before_sleep=f3,
        )
        def f4():
            n2["v"] += 1
            if n2["v"] < 3:
                raise ValueError("x")
            return "ok"

        f5 = f4.retry_with(sleep=None, wait=wait_fixed(2), stop=stop_after_attempt(3))
        out2 = f5()

        self.assertEqual(out2, "ok")
        self.assertEqual(c1.v, [])
        self.assertEqual(v2, [])
        self.assertAlmostEqual(f5.statistics["idle_for"], 4.0, places=5)


class TestB(unittest.TestCase):
    def setUp(self):
        self._old_sleep = tenacity.nap.sleep

    def tearDown(self):
        tenacity.nap.sleep = self._old_sleep

    @asynctest
    async def test_behavior_6(self):
        c1 = C1()
        tenacity.nap.sleep = c1

        r1 = AsyncRetrying(wait=wait_fixed(0.1), stop=stop_after_attempt(3))
        n1 = {"v": 0}

        async def f1():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            return "ok"

        out = await r1(f1)
        self.assertEqual(out, "ok")
        self.assertEqual(n1["v"], 3)
        self.assertEqual(c1.v, [])
        self.assertAlmostEqual(r1.statistics["idle_for"], 0.2, places=4)

    @asynctest
    async def test_behavior_7(self):
        v1 = []
        n1 = {"v": 0}

        def f1(s1):
            return a1(v1, ("w", s1.attempt_number), value=2.0)

        def f2(s1):
            return a1(v1, ("b", s1.attempt_number), value=None)

        r1 = AsyncRetrying(
            sleep=None,
            wait=f1,
            stop=stop_after_attempt(3),
            before_sleep=f2,
        )

        async def f3():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            return "ok"

        out = await r1(f3)
        self.assertEqual(out, "ok")
        self.assertEqual(v1, [("w", 1), ("w", 2)])
        self.assertAlmostEqual(r1.statistics["idle_for"], 4.0, places=5)

    @asynctest
    async def test_behavior_8(self):
        v1 = []
        n1 = {"v": 0}

        def f1(s1):
            return a1(v1, ("x", s1.attempt_number), value=None)

        def f2(s1):
            return a1(v1, ("y", s1.attempt_number), value=None)

        r1 = AsyncRetrying(
            sleep=None,
            wait=wait_none(),
            stop=stop_after_attempt(3),
            before=f1,
            after=f2,
        )

        async def f3():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            return "ok"

        out = await r1(f3)
        self.assertEqual(out, "ok")
        self.assertEqual(v1, [("x", 1), ("y", 1), ("x", 2), ("y", 2), ("x", 3)])

    @asynctest
    async def test_behavior_9(self):
        v1 = []

        def f1(s1):
            return a1(v1, ("r", s1.attempt_number), value=True)

        def f2(s1):
            return a1(v1, ("s", s1.attempt_number), value=(s1.attempt_number >= 3))

        def f3(s1):
            return a1(v1, ("e", s1.attempt_number), value="ok")

        r1 = AsyncRetrying(
            sleep=None,
            wait=wait_none(),
            retry=f1,
            stop=f2,
            retry_error_callback=f3,
        )

        async def f4():
            raise ValueError("x")

        out = await r1(f4)
        self.assertEqual(out, "ok")
        self.assertEqual(
            v1,
            [
                ("r", 1),
                ("s", 1),
                ("r", 2),
                ("s", 2),
                ("r", 3),
                ("s", 3),
                ("e", 3),
            ],
        )

    @asynctest
    async def test_behavior_10(self):
        v1 = []

        def f1(s1):
            return a1(v1, ("y", s1.attempt_number), value=None)

        def f2(s1):
            return a1(v1, ("e", s1.attempt_number), value="bad")

        r1 = AsyncRetrying(
            sleep=None,
            wait=wait_none(),
            stop=stop_after_attempt(3),
            after=f1,
            retry_error_callback=f2,
        )

        async def f3():
            raise ValueError("x")

        out = await r1(f3)
        self.assertEqual(out, "bad")
        self.assertEqual(v1, [("y", 1), ("y", 2), ("y", 3), ("e", 3)])


@unittest.skipUnless(HAS_TORNADO, "tornado not installed")
class TestC(unittest.TestCase):
    def setUp(self):
        self._old_sleep = tenacity.nap.sleep

    def tearDown(self):
        tenacity.nap.sleep = self._old_sleep

    def test_behavior_11(self):
        c1 = C1()
        tenacity.nap.sleep = c1

        r1 = TornadoRetrying(wait=wait_fixed(0.1), stop=stop_after_attempt(3))
        n1 = {"v": 0}

        @gen.coroutine
        def f1():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            raise gen.Return("ok")

        out = IOLoop().run_sync(lambda: r1(f1))
        self.assertEqual(out, "ok")
        self.assertEqual(n1["v"], 3)
        self.assertEqual(c1.v, [])
        self.assertAlmostEqual(r1.statistics["idle_for"], 0.2, places=4)

    def test_behavior_12(self):
        v1 = []
        n1 = {"v": 0}

        def f1(s1):
            return t1(v1, ("w", s1.attempt_number), value=2.0)

        def f2(s1):
            return t1(v1, ("b", s1.attempt_number), value=None)

        r1 = TornadoRetrying(
            sleep=None,
            wait=f1,
            stop=stop_after_attempt(3),
            before_sleep=f2,
        )

        @gen.coroutine
        def f3():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            raise gen.Return("ok")

        out = IOLoop().run_sync(lambda: r1(f3))
        self.assertEqual(out, "ok")
        self.assertEqual(v1, [("w", 1), ("w", 2)])
        self.assertAlmostEqual(r1.statistics["idle_for"], 4.0, places=5)

    def test_behavior_13(self):
        v1 = []
        n1 = {"v": 0}

        def f1(s1):
            return t1(v1, ("x", s1.attempt_number), value=None)

        def f2(s1):
            return t1(v1, ("y", s1.attempt_number), value=None)

        r1 = TornadoRetrying(
            sleep=None,
            wait=wait_none(),
            stop=stop_after_attempt(3),
            before=f1,
            after=f2,
        )

        @gen.coroutine
        def f3():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            raise gen.Return("ok")

        out = IOLoop().run_sync(lambda: r1(f3))
        self.assertEqual(out, "ok")
        self.assertEqual(v1, [("x", 1), ("y", 1), ("x", 2), ("y", 2), ("x", 3)])

    def test_behavior_14(self):
        v1 = []

        def f1(s1):
            return t1(v1, ("r", s1.attempt_number), value=True)

        def f2(s1):
            return t1(v1, ("s", s1.attempt_number), value=(s1.attempt_number >= 3))

        def f3(s1):
            return t1(v1, ("e", s1.attempt_number), value="ok")

        r1 = TornadoRetrying(
            sleep=None,
            wait=wait_none(),
            retry=f1,
            stop=f2,
            retry_error_callback=f3,
        )

        @gen.coroutine
        def f4():
            raise ValueError("x")

        out = IOLoop().run_sync(lambda: r1(f4))
        self.assertEqual(out, "ok")
        self.assertEqual(
            v1,
            [
                ("r", 1),
                ("s", 1),
                ("r", 2),
                ("s", 2),
                ("r", 3),
                ("s", 3),
                ("e", 3),
            ],
        )

    def test_behavior_15(self):
        v1 = []

        def f1(s1):
            return t1(v1, ("y", s1.attempt_number), value=None)

        def f2(s1):
            return t1(v1, ("e", s1.attempt_number), value="bad")

        r1 = TornadoRetrying(
            sleep=None,
            wait=wait_none(),
            stop=stop_after_attempt(3),
            after=f1,
            retry_error_callback=f2,
        )

        @gen.coroutine
        def f3():
            raise ValueError("x")

        out = IOLoop().run_sync(lambda: r1(f3))
        self.assertEqual(out, "bad")
        self.assertEqual(v1, [("y", 1), ("y", 2), ("y", 3), ("e", 3)])


class TestD(unittest.TestCase):
    def setUp(self):
        self._old_sleep = tenacity.nap.sleep

    def tearDown(self):
        tenacity.nap.sleep = self._old_sleep

    @staticmethod
    def _fail():
        raise ValueError("x")

    def test_behavior_16(self):
        c1 = C1()
        c2 = C1()
        tenacity.nap.sleep = c1
        r1 = Retrying(wait=wait_fixed(1), stop=stop_after_attempt(2))
        tenacity.nap.sleep = c2
        with self.assertRaises(RetryError):
            r1(self._fail)
        self.assertEqual(c1.v, [1.0])
        self.assertEqual(c2.v, [])

    def test_behavior_17(self):
        c1 = C1()
        r1 = Retrying(sleep=c1, wait=wait_fixed(1), stop=stop_after_attempt(2))
        r2 = r1.copy()
        with self.assertRaises(RetryError):
            r2(self._fail)
        self.assertEqual(c1.v, [1.0])

    def test_behavior_18(self):
        c1 = C1()

        @retry(sleep=c1, wait=wait_fixed(1), stop=stop_after_attempt(2))
        def f1():
            raise ValueError("x")

        f2 = f1.retry_with(stop=stop_after_attempt(2))
        with self.assertRaises(RetryError):
            f2()
        self.assertEqual(c1.v, [1.0])

    def test_behavior_19(self):
        seen = []

        def wait_fn(retry_state):
            seen.append(retry_state.attempt_number)
            return 1.5

        r1 = Retrying(sleep=None, wait=wait_fn, stop=stop_after_attempt(3))
        n1 = {"v": 0}

        def f1():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            return "ok"

        out = r1(f1)
        self.assertEqual(out, "ok")
        self.assertEqual(seen, [1, 2])
        self.assertAlmostEqual(r1.statistics["idle_for"], 3.0, places=5)

    def test_behavior_20(self):
        c1 = C1()
        seen = []

        def before_sleep(_):
            seen.append("called")

        @retry(sleep=c1, wait=wait_fixed(2), stop=stop_after_attempt(3), before_sleep=before_sleep)
        def f1():
            raise ValueError("x")

        f2 = f1.retry_with(sleep=None, stop=stop_after_attempt(3), wait=wait_fixed(2))
        with self.assertRaises(RetryError):
            f2()
        self.assertEqual(c1.v, [])
        self.assertEqual(seen, [])
        self.assertAlmostEqual(f2.statistics["idle_for"], 4.0, places=5)

    def test_behavior_21(self):
        c1 = C1()
        seen = []

        def before_sleep(retry_state):
            seen.append(retry_state.attempt_number)

        r1 = Retrying(sleep=c1, wait=wait_fixed(1), stop=stop_after_attempt(3), before_sleep=before_sleep)
        with self.assertRaises(RetryError):
            r1(self._fail)
        self.assertEqual(seen, [1, 2])

    def test_behavior_22(self):
        seen = []

        def before_sleep(retry_state):
            seen.append(retry_state.attempt_number)

        r1 = Retrying(sleep=None, wait=wait_fixed(1), stop=stop_after_attempt(3), before_sleep=before_sleep)
        with self.assertRaises(RetryError):
            r1(self._fail)
        self.assertEqual(seen, [])

    def test_behavior_23(self):
        c1 = C1()
        c2 = C1()
        tenacity.nap.sleep = c1

        @retry(wait=wait_fixed(1), stop=stop_after_attempt(2))
        def f1():
            raise ValueError("x")

        tenacity.nap.sleep = c2
        with self.assertRaises(RetryError):
            f1()
        self.assertEqual(c1.v, [1.0])
        self.assertEqual(c2.v, [])

    def test_behavior_24(self):
        c1 = C1()
        c2 = C1()
        tenacity.nap.sleep = c1

        @retry(wait=wait_fixed(1), stop=stop_after_attempt(2))
        def f1():
            raise ValueError("x")

        tenacity.nap.sleep = c2

        @retry(wait=wait_fixed(1), stop=stop_after_attempt(2))
        def f2():
            raise ValueError("x")

        with self.assertRaises(RetryError):
            f1()
        with self.assertRaises(RetryError):
            f2()
        self.assertEqual(c1.v, [1.0])
        self.assertEqual(c2.v, [1.0])

    def test_behavior_25(self):
        c1 = C1()
        tenacity.nap.sleep = c1

        @retry(wait=wait_fixed(2), stop=stop_after_attempt(3))
        def f1():
            raise ValueError("x")

        f2 = f1.retry_with(stop=stop_after_attempt(3))
        with self.assertRaises(RetryError):
            f2()
        self.assertEqual(c1.v, [2.0, 2.0])


class TestE(unittest.TestCase):
    def setUp(self):
        self._old_sleep = tenacity.nap.sleep

    def tearDown(self):
        tenacity.nap.sleep = self._old_sleep

    @asynctest
    async def test_behavior_26(self):
        v1 = []

        def f1(s1):
            return a1(v1, ("b", s1.attempt_number), value=None)

        r1 = AsyncRetrying(sleep=None, wait=wait_none(), stop=stop_after_attempt(2), before=f1)
        n1 = {"v": 0}

        async def f2():
            n1["v"] += 1
            if n1["v"] < 2:
                raise ValueError("x")
            return "ok"

        out = await r1(f2)
        self.assertEqual(out, "ok")
        self.assertEqual(v1, [("b", 1), ("b", 2)])

    @asynctest
    async def test_behavior_27(self):
        v1 = []

        def f1(s1):
            return a1(v1, ("a", s1.attempt_number), value=None)

        r1 = AsyncRetrying(sleep=None, wait=wait_none(), stop=stop_after_attempt(2), after=f1)

        async def f2():
            raise ValueError("x")

        with self.assertRaises(RetryError):
            await r1(f2)
        self.assertEqual(v1, [("a", 1), ("a", 2)])

    @asynctest
    async def test_behavior_28(self):
        calls = []

        def f1(s1):
            calls.append(s1.attempt_number)
            return a1([], ("w", s1.attempt_number), value=1.25)

        r1 = AsyncRetrying(sleep=None, wait=f1, stop=stop_after_attempt(3))
        n1 = {"v": 0}

        async def f2():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            return "ok"

        out = await r1(f2)
        self.assertEqual(out, "ok")
        self.assertEqual(calls, [1, 2])
        self.assertAlmostEqual(r1.statistics["idle_for"], 2.5, places=5)

    @asynctest
    async def test_behavior_29(self):
        v1 = []
        c1 = C2()

        def f1(s1):
            return a1(v1, ("bs", s1.attempt_number), value=None)

        r1 = AsyncRetrying(sleep=c1, wait=wait_fixed(0.5), stop=stop_after_attempt(3), before_sleep=f1)
        n1 = {"v": 0}

        async def f2():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            return "ok"

        out = await r1(f2)
        self.assertEqual(out, "ok")
        self.assertEqual(v1, [("bs", 1), ("bs", 2)])
        self.assertEqual(c1.v, [0.5, 0.5])

    @asynctest
    async def test_behavior_30(self):
        v1 = []

        def f1(s1):
            return a1(v1, ("r", s1.attempt_number), value=False)

        r1 = AsyncRetrying(sleep=None, wait=wait_none(), retry=f1, stop=stop_after_attempt(5))

        async def f2():
            raise ValueError("x")

        with self.assertRaises(ValueError):
            await r1(f2)
        self.assertEqual(v1, [("r", 1)])

    @asynctest
    async def test_behavior_31(self):
        v1 = []

        def f1(s1):
            return a1(v1, ("s", s1.attempt_number), value=(s1.attempt_number >= 2))

        r1 = AsyncRetrying(sleep=None, wait=wait_none(), stop=f1)

        async def f2():
            raise ValueError("x")

        with self.assertRaises(RetryError):
            await r1(f2)
        self.assertEqual(v1, [("s", 1), ("s", 2)])

    @asynctest
    async def test_behavior_32(self):
        def f1(_):
            return a1([], "cb", value="done")

        r1 = AsyncRetrying(
            sleep=None,
            wait=wait_none(),
            stop=stop_after_attempt(2),
            retry_error_callback=f1,
        )

        async def f2():
            raise ValueError("x")

        out = await r1(f2)
        self.assertEqual(out, "done")

    @asynctest
    async def test_behavior_33(self):
        c1 = C1()
        tenacity.nap.sleep = c1
        c2 = C2()
        r1 = AsyncRetrying(sleep=c2, wait=wait_fixed(0.1), stop=stop_after_attempt(3))
        n1 = {"v": 0}

        async def f1():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            return "ok"

        out = await r1(f1)
        self.assertEqual(out, "ok")
        self.assertEqual(c1.v, [])
        self.assertEqual(c2.v, [0.1, 0.1])

    @asynctest
    async def test_behavior_34(self):
        v1 = []

        def f1(s1):
            return a1(v1, ("bs", s1.attempt_number), value=None)

        r1 = AsyncRetrying(sleep=None, wait=wait_fixed(1), stop=stop_after_attempt(3), before_sleep=f1)

        async def f2():
            raise ValueError("x")

        with self.assertRaises(RetryError):
            await r1(f2)
        self.assertEqual(v1, [])
        self.assertAlmostEqual(r1.statistics["idle_for"], 2.0, places=5)

    @asynctest
    async def test_behavior_35(self):
        calls = []

        def f1(s1):
            calls.append(("before", s1.attempt_number))
            return a1([], ("x", s1.attempt_number), value=None)

        def f2(s1):
            calls.append(("after", s1.attempt_number))
            return a1([], ("y", s1.attempt_number), value=None)

        r1 = AsyncRetrying(sleep=None, wait=wait_none(), stop=stop_after_attempt(2), before=f1, after=f2)

        async def f3():
            raise ValueError("x")

        with self.assertRaises(RetryError):
            await r1(f3)
        self.assertEqual(calls, [("before", 1), ("after", 1), ("before", 2), ("after", 2)])


@unittest.skipUnless(HAS_TORNADO, "tornado not installed")
class TestF(unittest.TestCase):
    def setUp(self):
        self._old_sleep = tenacity.nap.sleep

    def tearDown(self):
        tenacity.nap.sleep = self._old_sleep

    def test_behavior_36(self):
        v1 = []

        def f1(s1):
            return t1(v1, ("b", s1.attempt_number), value=None)

        r1 = TornadoRetrying(sleep=None, wait=wait_none(), stop=stop_after_attempt(2), before=f1)
        n1 = {"v": 0}

        @gen.coroutine
        def f2():
            n1["v"] += 1
            if n1["v"] < 2:
                raise ValueError("x")
            raise gen.Return("ok")

        out = IOLoop().run_sync(lambda: r1(f2))
        self.assertEqual(out, "ok")
        self.assertEqual(v1, [("b", 1), ("b", 2)])

    def test_behavior_37(self):
        v1 = []

        def f1(s1):
            return t1(v1, ("a", s1.attempt_number), value=None)

        r1 = TornadoRetrying(sleep=None, wait=wait_none(), stop=stop_after_attempt(2), after=f1)

        @gen.coroutine
        def f2():
            raise ValueError("x")

        with self.assertRaises(RetryError):
            IOLoop().run_sync(lambda: r1(f2))
        self.assertEqual(v1, [("a", 1), ("a", 2)])

    def test_behavior_38(self):
        calls = []

        def f1(s1):
            calls.append(s1.attempt_number)
            return t1([], ("w", s1.attempt_number), value=1.25)

        r1 = TornadoRetrying(sleep=None, wait=f1, stop=stop_after_attempt(3))
        n1 = {"v": 0}

        @gen.coroutine
        def f2():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            raise gen.Return("ok")

        out = IOLoop().run_sync(lambda: r1(f2))
        self.assertEqual(out, "ok")
        self.assertEqual(calls, [1, 2])
        self.assertAlmostEqual(r1.statistics["idle_for"], 2.5, places=5)

    def test_behavior_39(self):
        v1 = []
        c1 = C1()

        def f1(s1):
            return t1(v1, ("bs", s1.attempt_number), value=None)

        r1 = TornadoRetrying(sleep=c1, wait=wait_fixed(0.5), stop=stop_after_attempt(3), before_sleep=f1)
        n1 = {"v": 0}

        @gen.coroutine
        def f2():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            raise gen.Return("ok")

        out = IOLoop().run_sync(lambda: r1(f2))
        self.assertEqual(out, "ok")
        self.assertEqual(v1, [("bs", 1), ("bs", 2)])
        self.assertEqual(c1.v, [0.5, 0.5])

    def test_behavior_40(self):
        v1 = []

        def f1(s1):
            return t1(v1, ("r", s1.attempt_number), value=False)

        r1 = TornadoRetrying(sleep=None, wait=wait_none(), retry=f1, stop=stop_after_attempt(5))

        @gen.coroutine
        def f2():
            raise ValueError("x")

        with self.assertRaises(ValueError):
            IOLoop().run_sync(lambda: r1(f2))
        self.assertEqual(v1, [("r", 1)])

    def test_behavior_46(self):
        calls = []
        n1 = {"v": 0}

        @gen.coroutine
        def wait_fn(retry_state):
            calls.append(("w", retry_state.attempt_number))
            raise gen.Return(t1([], ("inner", retry_state.attempt_number), value=1.0))

        r1 = TornadoRetrying(sleep=None, wait=wait_fn, stop=stop_after_attempt(3))

        @gen.coroutine
        def f1():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            raise gen.Return("ok")

        out = IOLoop().run_sync(lambda: r1(f1))
        self.assertEqual(out, "ok")
        self.assertEqual(calls, [("w", 1), ("w", 2)])
        self.assertAlmostEqual(r1.statistics["idle_for"], 2.0, places=5)


class TestG(unittest.TestCase):
    def setUp(self):
        self._old_sleep = tenacity.nap.sleep

    def tearDown(self):
        tenacity.nap.sleep = self._old_sleep

    def test_behavior_41(self):
        seen_wait = []
        seen_before_sleep = []
        r1 = Retrying(
            sleep=None,
            wait=lambda s1: seen_wait.append(s1.attempt_number) or 1.5,
            stop=stop_after_attempt(3),
            before_sleep=lambda s1: seen_before_sleep.append(s1.attempt_number),
        )
        n1 = {"v": 0}

        for attempt in r1:
            with attempt:
                n1["v"] += 1
                if n1["v"] < 3:
                    raise ValueError("x")

        self.assertEqual(n1["v"], 3)
        self.assertEqual(seen_wait, [1, 2])
        self.assertEqual(seen_before_sleep, [])
        self.assertAlmostEqual(r1.statistics["idle_for"], 3.0, places=5)

    def test_behavior_42(self):
        c1 = C1()
        c2 = C1()
        tenacity.nap.sleep = c1
        r1 = Retrying(wait=wait_fixed(1), stop=stop_after_attempt(3))
        tenacity.nap.sleep = c2
        n1 = {"v": 0}

        with self.assertRaises(RetryError):
            for attempt in r1:
                with attempt:
                    n1["v"] += 1
                    raise ValueError("x")

        self.assertEqual(n1["v"], 3)
        self.assertEqual(c1.v, [1.0, 1.0])
        self.assertEqual(c2.v, [])


class TestH(unittest.TestCase):
    def setUp(self):
        self._old_sleep = tenacity.nap.sleep

    def tearDown(self):
        tenacity.nap.sleep = self._old_sleep

    @asynctest
    async def test_behavior_43(self):
        seen_wait = []
        seen_before_sleep = []
        r1 = AsyncRetrying(
            sleep=None,
            wait=lambda s1: seen_wait.append(s1.attempt_number) or a1([], ("w", s1.attempt_number), value=1.25),
            stop=stop_after_attempt(3),
            before_sleep=lambda s1: seen_before_sleep.append(s1.attempt_number) or a1([], ("b", s1.attempt_number), value=None),
        )
        n1 = {"v": 0}

        async for attempt in r1:
            with attempt:
                n1["v"] += 1
                if n1["v"] < 3:
                    raise ValueError("x")

        self.assertEqual(n1["v"], 3)
        self.assertEqual(seen_wait, [1, 2])
        self.assertEqual(seen_before_sleep, [])
        self.assertAlmostEqual(r1.statistics["idle_for"], 2.5, places=5)

    @asynctest
    async def test_behavior_44(self):
        seen = []
        r1 = AsyncRetrying(
            sleep=None,
            wait=wait_none(),
            retry=lambda s1: a1(seen, ("r", s1.attempt_number), value=True),
            stop=lambda s1: a1(seen, ("s", s1.attempt_number), value=(s1.attempt_number >= 2)),
        )

        with self.assertRaises(RetryError):
            async for attempt in r1:
                with attempt:
                    raise ValueError("x")

        self.assertEqual(seen, [("r", 1), ("s", 1), ("r", 2), ("s", 2)])

    @asynctest
    async def test_behavior_45(self):
        calls = []
        n1 = {"v": 0}

        async def wait_fn(retry_state):
            calls.append(("w", retry_state.attempt_number))
            return a1([], ("inner", retry_state.attempt_number), value=1.0)

        r1 = AsyncRetrying(sleep=None, wait=wait_fn, stop=stop_after_attempt(3))

        async def f1():
            n1["v"] += 1
            if n1["v"] < 3:
                raise ValueError("x")
            return "ok"

        out = await r1(f1)
        self.assertEqual(out, "ok")
        self.assertEqual(calls, [("w", 1), ("w", 2)])
        self.assertAlmostEqual(r1.statistics["idle_for"], 2.0, places=5)
