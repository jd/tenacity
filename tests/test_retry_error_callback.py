import asyncio

import pytest

from tenacity import (
    AsyncRetrying,
    RetryCallState,
    RetryError,
    Retrying,
    stop_after_attempt,
)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_falsey_retry_error_callback(asynchronous: bool) -> None:
    attempts: list[int] = []
    callback_states: list[RetryCallState] = []

    class Callback:
        def __bool__(self) -> bool:
            return False

        def __call__(self, retry_state: RetryCallState) -> str:
            callback_states.append(retry_state)
            return "fallback"

    def fails() -> str:
        attempts.append(len(attempts) + 1)
        raise ValueError("retry")

    result: str
    if asynchronous:

        async def async_fails() -> str:
            return fails()

        result = asyncio.run(
            AsyncRetrying(stop=stop_after_attempt(3), retry_error_callback=Callback())(
                async_fails
            )
        )
    else:
        result = Retrying(stop=stop_after_attempt(3), retry_error_callback=Callback())(
            fails
        )

    assert result == "fallback"
    assert attempts == [1, 2, 3]
    assert len(callback_states) == 1
    assert callback_states[0].attempt_number == 3
    assert callback_states[0].outcome is not None
    assert isinstance(callback_states[0].outcome.exception(), ValueError)


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("callback", [False, 0, ""])
def test_falsey_noncallable_retry_error_callback(
    asynchronous: bool, callback: bool | int | str
) -> None:
    def fails() -> str:
        raise ValueError("retry")

    with pytest.raises(RetryError) as exc_info:
        if asynchronous:

            async def async_fails() -> str:
                return fails()

            asyncio.run(
                AsyncRetrying(
                    stop=stop_after_attempt(2),
                    retry_error_callback=callback,  # type: ignore[arg-type]
                )(async_fails)
            )
        else:
            Retrying(
                stop=stop_after_attempt(2),
                retry_error_callback=callback,  # type: ignore[arg-type]
            )(fails)

    assert exc_info.value.last_attempt.attempt_number == 2
    assert isinstance(exc_info.value.last_attempt.exception(), ValueError)


def test_falsey_async_retry_error_callback() -> None:
    callback_states: list[RetryCallState] = []

    class Callback:
        def __bool__(self) -> bool:
            return False

        async def __call__(self, retry_state: RetryCallState) -> str:
            await asyncio.sleep(0)
            callback_states.append(retry_state)
            return "fallback"

    async def fails() -> str:
        raise ValueError("retry")

    result: str = asyncio.run(
        AsyncRetrying(stop=stop_after_attempt(2), retry_error_callback=Callback())(
            fails
        )
    )
    assert result == "fallback"
    assert len(callback_states) == 1
    assert callback_states[0].attempt_number == 2
