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

import six

from tenacity import _utils


def before_sleep_nothing(call_state, sleep, last_result):
    """Before call strategy that does nothing."""


def before_sleep_log(logger, log_level):
    """Before call strategy that logs to some logger the attempt."""
    def log_it(call_state):
        logger.log(log_level,
                   "Retrying %s in %d seconds as it raised %s.",
                   _utils.get_callback_name(call_state.fn),
                   getattr(call_state.next_action, 'sleep'),
                   call_state.outcome.exception())
    return log_it


def _before_sleep_func_accept_call_state(fn):
    if not six.callable(fn):
        return fn

    takes_call_state = _utils._func_takes_call_state(fn)
    if takes_call_state:
        return fn

    @six.wraps(fn)
    def wrapped_before_sleep_func(call_state):
        return fn(
            call_state.retry_object,
            sleep=getattr(call_state.next_action, 'sleep'),
            last_result=call_state.outcome)
    return wrapped_before_sleep_func
