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
    import logging

    from tenacity import RetryCallState


def before_nothing(retry_state: "RetryCallState") -> None:
    """Before call strategy that does nothing."""


def before_log(logger: "logging.Logger", log_level: int) -> typing.Callable[["RetryCallState"], None]:  # noqa:BLK100
    """Before call strategy that logs to some logger the attempt."""

    def log_it(retry_state: "RetryCallState") -> None:
        logger.log(
            log_level,
            "Starting call to '{0}', this is the {1} time calling it.".format(
                _utils.get_callback_name(retry_state.fn),
                _utils.to_ordinal(retry_state.attempt_number),
            ),
        )

    return log_it
