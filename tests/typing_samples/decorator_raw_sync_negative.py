# pyright: strict

from typing import Callable
from typing_extensions import assert_type

from tenacity import Retrying
from tenacity import retry


def base(count: int, text: str) -> str:
    return f"{count}:{text}"


wrapped = retry(base)
assert_type(wrapped.retry, Retrying)
wrong_wrapped: Callable[[str, int], str] = wrapped  # EXPECTED_PYRIGHT_ERROR
