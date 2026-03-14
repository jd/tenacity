# pyright: strict

from typing import Any
from typing import Callable
from typing import Coroutine
from typing_extensions import assert_type

from tenacity import retry
from tenacity import stop_after_attempt
from tenacity.asyncio import AsyncRetrying


async def base(count: int, text: str) -> str:
    return f"{count}:{text}"


wrapped = retry(base)
configured = wrapped.retry_with(stop=stop_after_attempt(2))
assert_type(configured.retry, AsyncRetrying)
wrong_configured: Callable[[str, int], Coroutine[Any, Any, str]] = configured  # EXPECTED_PYRIGHT_ERROR
