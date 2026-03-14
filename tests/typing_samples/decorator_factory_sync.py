# pyright: strict

from typing import Any
from typing import Callable
from typing_extensions import assert_type

from tenacity import Retrying
from tenacity import retry
from tenacity import stop_after_attempt
from tenacity import wait_fixed


def takes_sync(fn: Callable[[int, str], str]) -> str:
    return fn(1, "alpha")


def controller_name(value: Retrying) -> str:
    return value.__class__.__name__


def count_entries(value: dict[str, Any]) -> int:
    return len(value)


@retry(stop=stop_after_attempt(1), wait=wait_fixed(0))
def wrapped(count: int, text: str) -> str:
    return f"{count}:{text}"


controller_name_result = controller_name(wrapped.retry)
stats_size_result = count_entries(wrapped.statistics)
call_result = wrapped(2, "beta")
callable_result = takes_sync(wrapped)

configured = wrapped.retry_with(stop=stop_after_attempt(2))
configured_controller_name_result = controller_name(configured.retry)
configured_stats_size_result = count_entries(configured.statistics)
configured_call_result = configured(3, "gamma")
configured_callable_result = takes_sync(configured)
reconfigured = configured.retry_with(wait=wait_fixed(3))
reconfigured_controller_name_result = controller_name(reconfigured.retry)
reconfigured_stats_size_result = count_entries(reconfigured.statistics)
reconfigured_call_result = reconfigured(4, "delta")
reconfigured_callable_result = takes_sync(reconfigured)

assert_type(wrapped.retry, Retrying)
assert_type(wrapped.statistics, dict[str, Any])
assert_type(call_result, str)
assert_type(callable_result, str)
assert_type(controller_name_result, str)
assert_type(stats_size_result, int)
assert_type(configured.retry, Retrying)
assert_type(configured.statistics, dict[str, Any])
assert_type(configured_call_result, str)
assert_type(configured_callable_result, str)
assert_type(configured_controller_name_result, str)
assert_type(configured_stats_size_result, int)
assert_type(reconfigured.retry, Retrying)
assert_type(reconfigured.statistics, dict[str, Any])
assert_type(reconfigured_call_result, str)
assert_type(reconfigured_callable_result, str)
assert_type(reconfigured_controller_name_result, str)
assert_type(reconfigured_stats_size_result, int)
