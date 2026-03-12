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

import traceback
import typing

from tenacity import _utils

if typing.TYPE_CHECKING:
    from tenacity import RetryCallState


def before_sleep_nothing(retry_state: "RetryCallState") -> None:
    """Before sleep strategy that does nothing."""


def before_sleep_log(
    logger: _utils.LoggerProtocol,
    log_level: int,
    exc_info: bool = False,
    sec_format: str = "%.3g",
) -> typing.Callable[["RetryCallState"], None]:
    """Before sleep strategy that logs to some logger the attempt."""

    def log_it(retry_state: "RetryCallState") -> None:
        if retry_state.outcome is None:
            raise RuntimeError("log_it() called before outcome was set")

        if retry_state.next_action is None:
            raise RuntimeError("log_it() called before next_action was set")

        if retry_state.outcome.failed:
            ex = retry_state.outcome.exception()
            verb, value = "raised", f"{ex.__class__.__name__}: {ex}"
        else:
            verb, value = "returned", retry_state.outcome.result()

        fn_name = retry_state.get_fn_name()

        msg = (
            f"Retrying {fn_name} "
            f"in {sec_format % retry_state.next_action.sleep} seconds as it {verb} {value}."
        )

        if exc_info and retry_state.outcome.failed:
            ex = retry_state.outcome.exception()
            if ex is not None:
                tb = "".join(traceback.format_exception(type(ex), ex, ex.__traceback__))
                msg = f"{msg}\n{tb.rstrip()}"

        logger.log(log_level, msg)

    return log_it
