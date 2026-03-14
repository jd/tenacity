# pyright: strict

from typing import Any
from typing import Callable
from typing import Coroutine
from typing_extensions import assert_type

from tenacity import retry
from tenacity import stop_after_attempt
from tenacity import wait_fixed
from tenacity.asyncio import AsyncRetrying


@retry(stop=stop_after_attempt(1), wait=wait_fixed(0))
async def wrapped(count: int, text: str) -> str:
    return f"{count}:{text}"


configured = wrapped.retry_with(stop=stop_after_attempt(2))
assert_type(configured.retry, AsyncRetrying)
wrong_configured: Callable[[str, int], Coroutine[Any, Any, str]] = configured  # EXPECTED_PYRIGHT_ERROR
