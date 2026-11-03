# Copyright 2016–2021 Julien Danjou
# Copyright 2016 Joshua Harlow
# Copyright 2013-2014 Ray Holder
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Regression tests for retry_if_exception_cause_type.

These tests check that the retry predicate follows implicit exception
chains (``__context__``), not only explicit ones (``__cause__``).

When an exception is raised inside an ``except`` block without an explicit
``raise ... from ...``, Python sets ``__context__`` (and ``__suppress_context__``
is ``False``) but leaves ``__cause__`` as ``None``. Tracebacks render the
chain ("During handling of the above exception, another exception occurred"),
so a user asking to retry when the underlying cause is e.g. a ``NameError``
naturally expects both spellings to behave identically.
"""

import typing

import tenacity


def _retry_call(
    fn: typing.Callable[..., typing.Any], /, *args: typing.Any, **kwargs: typing.Any
) -> typing.Any:
    r = tenacity.Retrying(
        wait=tenacity.wait_fixed(0),
        retry=tenacity.retry_if_exception_cause_type(NameError),
        stop=tenacity.stop_after_attempt(50),
    )
    return r(fn, *args, **kwargs)


class _ImplicitNameErrorCauseAfterCount:
    """Raise a wrapper error raised implicitly during NameError handling."""

    def __init__(self, count: int) -> None:
        self.count = count
        self.current_count = 0

    def go(self) -> int:
        self.current_count += 1
        if self.current_count < self.count:
            try:
                raise NameError("NameError cause")
            except NameError:
                # No explicit `from`: sets __context__, not __cause__.
                raise ValueError("implicit chain")  # noqa: B904
        return self.current_count


class _ExplicitNameErrorCauseAfterCount:
    """Raise a wrapper error raised explicitly from a NameError."""

    def __init__(self, count: int) -> None:
        self.count = count
        self.current_count = 0

    def go(self) -> int:
        self.current_count += 1
        if self.current_count < self.count:
            try:
                raise NameError("NameError cause")
            except NameError as exc:
                # Explicit `from`: sets __cause__ (and __context__).
                raise ValueError("explicit chain") from exc
        return self.current_count


def test_implicit_context_chain_is_retried() -> None:
    """retry_if_exception_cause_type must retry on implicit __context__ chains."""
    thing = _ImplicitNameErrorCauseAfterCount(5)
    result = _retry_call(thing.go)
    assert result == 5
    assert thing.current_count == 5


def test_explicit_cause_chain_is_retried() -> None:
    """Explicit __cause__ chains keep working (guard against regressions)."""
    thing = _ExplicitNameErrorCauseAfterCount(5)
    result = _retry_call(thing.go)
    assert result == 5
    assert thing.current_count == 5


def test_implicit_context_chain_without_matching_cause_stops() -> None:
    """Non-matching implicit chains must still not be retried."""
    attempts = []

    def go() -> None:
        attempts.append(1)
        if len(attempts) < 3:
            try:
                raise OSError("os error")
            except OSError:
                raise ValueError("implicit chain, non-matching cause")  # noqa: B904

    r = tenacity.Retrying(
        wait=tenacity.wait_fixed(0),
        retry=tenacity.retry_if_exception_cause_type(NameError),
        stop=tenacity.stop_after_attempt(50),
    )
    try:
        r(go)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError to propagate")
    assert len(attempts) == 1


def test_non_matching_cause_stops() -> None:
    """A plain exception without any matching cause must not be retried."""
    attempts = []

    def go() -> None:
        attempts.append(1)
        if len(attempts) < 3:
            raise NameError("raised directly, no cause")

    r = tenacity.Retrying(
        wait=tenacity.wait_fixed(0),
        retry=tenacity.retry_if_exception_cause_type(OSError),
        stop=tenacity.stop_after_attempt(50),
    )
    try:
        r(go)
    except NameError:
        pass
    else:
        raise AssertionError("expected NameError to propagate")
    assert len(attempts) == 1


if __name__ == "__main__":
    test_implicit_context_chain_is_retried()
    test_explicit_cause_chain_is_retried()
    test_implicit_context_chain_without_matching_cause_stops()
    test_non_matching_cause_stops()
    print("all regression tests passed")
