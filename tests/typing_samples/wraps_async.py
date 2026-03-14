# pyright: strict

from typing import Any
from typing import Callable
from typing import Coroutine
from typing_extensions import assert_type

from tenacity import stop_after_attempt
from tenacity import wait_fixed
from tenacity.asyncio import AsyncRetrying


def takes_async(fn: Callable[[int, str], Coroutine[Any, Any, str]]) -> Coroutine[Any, Any, str]:
    return fn(1, "alpha")


def controller_name(value: AsyncRetrying) -> str:
    return value.__class__.__name__


def count_entries(value: dict[str, Any]) -> int:
    return len(value)


def consume_async_result(value: Coroutine[Any, Any, str]) -> None:
    pass


async def base(count: int, text: str) -> str:
    return f"{count}:{text}"


wrapped = AsyncRetrying(stop=stop_after_attempt(1), wait=wait_fixed(0)).wraps(base)

controller_name_result = controller_name(wrapped.retry)
stats_size_result = count_entries(wrapped.statistics)
call_result = wrapped(2, "beta")
callable_result = takes_async(wrapped)

configured = wrapped.retry_with(stop=stop_after_attempt(2))
configured_controller_name_result = controller_name(configured.retry)
configured_stats_size_result = count_entries(configured.statistics)
configured_call_result = configured(3, "gamma")
configured_callable_result = takes_async(configured)
reconfigured = configured.retry_with(wait=wait_fixed(3))
reconfigured_controller_name_result = controller_name(reconfigured.retry)
reconfigured_stats_size_result = count_entries(reconfigured.statistics)
reconfigured_call_result = reconfigured(4, "delta")
reconfigured_callable_result = takes_async(reconfigured)

assert_type(wrapped.retry, AsyncRetrying)
assert_type(wrapped.statistics, dict[str, Any])
consume_async_result(call_result)
consume_async_result(callable_result)
assert_type(controller_name_result, str)
assert_type(stats_size_result, int)
assert_type(configured.retry, AsyncRetrying)
assert_type(configured.statistics, dict[str, Any])
consume_async_result(configured_call_result)
consume_async_result(configured_callable_result)
assert_type(configured_controller_name_result, str)
assert_type(configured_stats_size_result, int)
assert_type(reconfigured.retry, AsyncRetrying)
assert_type(reconfigured.statistics, dict[str, Any])
consume_async_result(reconfigured_call_result)
consume_async_result(reconfigured_callable_result)
assert_type(reconfigured_controller_name_result, str)
assert_type(reconfigured_stats_size_result, int)
