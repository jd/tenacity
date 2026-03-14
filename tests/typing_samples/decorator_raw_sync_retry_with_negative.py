# pyright: strict

from typing import Callable
from typing_extensions import assert_type

from tenacity import Retrying
from tenacity import retry
from tenacity import stop_after_attempt


def base(count: int, text: str) -> str:
    return f"{count}:{text}"


wrapped = retry(base)
configured = wrapped.retry_with(stop=stop_after_attempt(2))
assert_type(configured.retry, Retrying)
wrong_configured: Callable[[str, int], str] = configured  # EXPECTED_PYRIGHT_ERROR
