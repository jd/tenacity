# pyright: strict

from typing import Callable
from typing_extensions import assert_type

from tenacity import Retrying
from tenacity import stop_after_attempt
from tenacity import wait_fixed


def base(count: int, text: str) -> str:
    return f"{count}:{text}"


wrapped = Retrying(stop=stop_after_attempt(1), wait=wait_fixed(0)).wraps(base)
configured = wrapped.retry_with(stop=stop_after_attempt(2))
assert_type(configured.retry, Retrying)
wrong_configured: Callable[[str, int], str] = configured  # EXPECTED_PYRIGHT_ERROR
