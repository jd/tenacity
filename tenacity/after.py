# Copyright 2016 Julien Danjou
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

import typing

from tenacity import _utils

if typing.TYPE_CHECKING:
    from tenacity import RetryCallState


def after_nothing(retry_state: "RetryCallState") -> None:
    """After call strategy that does nothing."""


def after_log(
    logger: _utils.LoggerProtocol,
    log_level: int,
    sec_format: str = "%.3g",
) -> typing.Callable[["RetryCallState"], None]:
    """After call strategy that logs to some logger the finished attempt."""

    def log_it(retry_state: "RetryCallState") -> None:
        fn_name = retry_state.get_fn_name()
        secs = retry_state.seconds_since_start
        logger.log(
            log_level,
            f"Finished call to '{fn_name}' "
            f"after {sec_format % secs if secs is not None else '?'}(s), "
            f"this was the {_utils.to_ordinal(retry_state.attempt_number)} time calling it.",
        )

    return log_it


def success_nothing(retry_state: "RetryCallState") -> None:
    """Success strategy that does nothing."""


def success_log(
    logger: _utils.LoggerProtocol,
    log_level: int,
    sec_format: str = "%.3g",
    *,
    only_if_retried: bool = True,
) -> typing.Callable[["RetryCallState"], None]:
    """Log when a retried call ultimately succeeds.

    Unlike :func:`after_log` (which runs only on *failed* attempts that will
    be retried — see the retry controller), this callback runs on the
    successful exit path. Set ``only_if_retried=False`` to also log first-try
    successes.

    Addresses the common need to emit a "retry_success" line only when
    recovery actually happened (GitHub #531 / Stack Overflow).
    """

    def log_it(retry_state: "RetryCallState") -> None:
        if only_if_retried and retry_state.attempt_number <= 1:
            return
        fn_name = retry_state.get_fn_name()
        secs = retry_state.seconds_since_start
        logger.log(
            log_level,
            f"Successful call to '{fn_name}' "
            f"after {sec_format % secs if secs is not None else '?'}(s), "
            f"this was the {_utils.to_ordinal(retry_state.attempt_number)} time calling it.",
        )

    return log_it
