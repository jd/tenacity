# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any

import pytest

from tenacity import AsyncRetrying, RetryCallState, Retrying, stop_after_attempt
from tenacity._utils import override
from tenacity.asyncio.retry import (
    async_retry_base,
)
from tenacity.asyncio.retry import (
    retry_all as async_retry_all,
)
from tenacity.asyncio.retry import (
    retry_any as async_retry_any,
)
from tenacity.asyncio.retry import (
    retry_if_result as async_retry_if_result,
)
from tenacity.retry import RetryBaseT, retry_all, retry_any, retry_base, retry_if_result

from .test_asyncio import asynctest


@pytest.mark.parametrize("kind", ["or", "and"])
@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("other_kind", ["strategy", "composite", "callable"])
@pytest.mark.parametrize("terminal", [False, True])
def test_retry_composition_preserves_subclass(
    kind: str, side: str, other_kind: str, terminal: bool
) -> None:
    calls: list[str] = []
    neutral = kind == "and"

    def unexpected(state: RetryCallState) -> bool:
        pytest.fail("Composition must not bypass the subclass's __call__")

    class CustomAny(retry_any):
        @override
        def __call__(self, retry_state: RetryCallState) -> bool:
            calls.append("custom")
            return not neutral if terminal else neutral

    class CustomAll(retry_all):
        @override
        def __call__(self, retry_state: RetryCallState) -> bool:
            calls.append("custom")
            return not neutral if terminal else neutral

    custom = CustomAny(unexpected) if kind == "or" else CustomAll(unexpected)

    def other_call(value: Any) -> bool:
        calls.append("other")
        return neutral

    other: RetryBaseT
    if other_kind == "callable":
        other = other_call
    elif other_kind == "composite":
        other = retry_any(other_call) if kind == "or" else retry_all(other_call)
    else:
        other = retry_if_result(other_call)

    if side == "left":
        combined = custom | other if kind == "or" else custom & other
        expected_calls = ["custom"] if terminal else ["custom", "other"]
    else:
        combined = other | custom if kind == "or" else other & custom
        expected_calls = ["other", "custom"]

    state = RetryCallState(Retrying(), None, (), {})
    state.set_result(None)
    assert combined(state) is (not neutral if terminal else neutral)
    assert calls == expected_calls


@pytest.mark.parametrize("kind", ["or", "and"])
@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize(
    "other_kind",
    ["sync_strategy", "async_strategy", "sync_composite", "async_composite"],
)
@pytest.mark.parametrize("terminal", [False, True])
@asynctest
async def test_async_retry_composition_preserves_subclass(
    kind: str, side: str, other_kind: str, terminal: bool
) -> None:
    calls: list[str] = []
    neutral = kind == "and"

    async def unexpected(value: Any) -> bool:
        pytest.fail("Composition must not bypass the subclass's __call__")

    class CustomAny(async_retry_any):
        @override
        async def __call__(self, retry_state: RetryCallState) -> bool:  # type: ignore[override]
            calls.append("custom")
            return not neutral if terminal else neutral

    class CustomAll(async_retry_all):
        @override
        async def __call__(self, retry_state: RetryCallState) -> bool:  # type: ignore[override]
            calls.append("custom")
            return not neutral if terminal else neutral

    leaf = async_retry_if_result(unexpected)
    custom = CustomAny(leaf) if kind == "or" else CustomAll(leaf)

    def sync_other(value: Any) -> bool:
        calls.append("other")
        return neutral

    async def async_other(value: Any) -> bool:
        calls.append("other")
        return neutral

    other = retry_if_result(sync_other)
    async_other_strategy: async_retry_base = async_retry_if_result(async_other)
    other_strategy: retry_base
    if other_kind == "sync_composite":
        other_strategy = retry_any(other) if kind == "or" else retry_all(other)
    else:
        other_strategy = other
    if other_kind == "async_composite":
        async_other_strategy = (
            async_retry_any(async_other_strategy)
            if kind == "or"
            else async_retry_all(async_other_strategy)
        )

    combined: retry_base
    if other_kind.startswith("sync"):
        if side == "left":
            combined = (
                custom | other_strategy if kind == "or" else custom & other_strategy
            )
        else:
            combined = (
                other_strategy | custom if kind == "or" else other_strategy & custom
            )
    elif side == "left":
        combined = (
            custom | async_other_strategy
            if kind == "or"
            else custom & async_other_strategy
        )
    else:
        combined = (
            async_other_strategy | custom
            if kind == "or"
            else async_other_strategy & custom
        )

    state = RetryCallState(AsyncRetrying(), None, (), {})
    state.set_result(None)
    assert isinstance(combined, async_retry_base)
    assert await combined(state) is (not neutral if terminal else neutral)
    if side == "right":
        assert calls == ["other", "custom"]
    else:
        assert calls == (["custom"] if terminal else ["custom", "other"])


@pytest.mark.parametrize("kind", ["or", "and"])
def test_retry_composite_subclass_controls_retry_loop(kind: str) -> None:
    class RetryOnceAny(retry_any):
        @override
        def __call__(self, retry_state: RetryCallState) -> bool:
            return retry_state.attempt_number == 1

    class RetryOnceAll(retry_all):
        @override
        def __call__(self, retry_state: RetryCallState) -> bool:
            return retry_state.attempt_number == 1

    neutral = retry_if_result(lambda value: kind == "and")
    custom = RetryOnceAny(neutral) if kind == "or" else RetryOnceAll(neutral)
    combined = neutral | custom if kind == "or" else neutral & custom
    retrying = Retrying(retry=combined, stop=stop_after_attempt(3))
    assert retrying(lambda: "result") == "result"
    assert retrying.statistics["attempt_number"] == 2


@pytest.mark.parametrize("kind", ["or", "and"])
@asynctest
async def test_async_retry_composite_subclass_controls_retry_loop(kind: str) -> None:
    class RetryOnceAny(async_retry_any):
        @override
        async def __call__(self, retry_state: RetryCallState) -> bool:  # type: ignore[override]
            return retry_state.attempt_number == 1

    class RetryOnceAll(async_retry_all):
        @override
        async def __call__(self, retry_state: RetryCallState) -> bool:  # type: ignore[override]
            return retry_state.attempt_number == 1

    neutral = retry_if_result(lambda value: kind == "and")
    custom = RetryOnceAny(neutral) if kind == "or" else RetryOnceAll(neutral)
    combined = neutral | custom if kind == "or" else neutral & custom
    retrying = AsyncRetrying(retry=combined, stop=stop_after_attempt(3))

    async def target() -> str:
        return "result"

    assert await retrying(target) == "result"
    assert retrying.statistics["attempt_number"] == 2


@pytest.mark.parametrize("kind", ["or", "and"])
@pytest.mark.parametrize(
    "shape", ["left", "right", "both", "callable_left", "callable_right"]
)
def test_retry_composition_still_coalesces_builtins(kind: str, shape: str) -> None:
    neutral = kind == "and"
    calls: list[str] = []

    def predicate(name: str) -> RetryBaseT:
        def call(value: Any) -> bool:
            calls.append(name)
            return neutral

        return call

    a, b, c, d = (retry_if_result(predicate(name)) for name in "abcd")
    composite = retry_any if kind == "or" else retry_all
    left, right = composite(a, b), composite(c, d)
    expected: tuple[RetryBaseT, ...]
    if shape == "left":
        combined = left | c if kind == "or" else left & c
        expected = (a, b, c)
        expected_calls = list("abc")
    elif shape == "right":
        combined = b | right if kind == "or" else b & right
        expected = (b, c, d)
        expected_calls = list("bcd")
    elif shape == "both":
        combined = left | right if kind == "or" else left & right
        expected = (a, b, c, d)
        expected_calls = list("abcd")
    elif shape == "callable_left":
        callback = predicate("b")
        combined = callback | right if kind == "or" else callback & right
        expected = (callback, c, d)
        expected_calls = list("bcd")
    else:
        callback = predicate("c")
        combined = left | callback if kind == "or" else left & callback
        expected = (a, b, callback)
        expected_calls = list("abc")

    assert combined.retries == expected
    state = RetryCallState(Retrying(), None, (), {})
    state.set_result(None)
    assert combined(state) is neutral
    assert calls == expected_calls
