# pyright: strict

from typing import Callable
from typing_extensions import assert_type

from tenacity import Retrying
from tenacity import stop_after_attempt
from tenacity import wait_fixed


def base(count: int, text: str) -> str:
    return f"{count}:{text}"


wrapped = Retrying(stop=stop_after_attempt(1), wait=wait_fixed(0)).wraps(base)
assert_type(wrapped.retry, Retrying)
wrong_wrapped: Callable[[str, int], str] = wrapped  # EXPECTED_PYRIGHT_ERROR
