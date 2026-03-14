# pyright: strict

from typing import Any
from typing import Callable
from typing import Coroutine
from typing_extensions import assert_type

from tenacity import retry
from tenacity.asyncio import AsyncRetrying


async def base(count: int, text: str) -> str:
    return f"{count}:{text}"


wrapped = retry(base)
assert_type(wrapped.retry, AsyncRetrying)
wrong_wrapped: Callable[[str, int], Coroutine[Any, Any, str]] = wrapped  # EXPECTED_PYRIGHT_ERROR
