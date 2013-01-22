## Copyright 2013 Ray Holder
##
## Licensed under the Apache License, Version 2.0 (the "License");
## you may not use this file except in compliance with the License.
## You may obtain a copy of the License at
##
## http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing, software
## distributed under the License is distributed on an "AS IS" BASIS,
## WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
## See the License for the specific language governing permissions and
## limitations under the License.

import random
import time

# sys.maxint / 2, since Python 3.2 doesn't have a sys.maxint...
MAX_WAIT = 1073741823

def retry(*dargs, **dkw):
    """
    TODO comment
    """
    def wrap(f):
        def wrapped_f(*args, **kw):
            return Retrying(*dargs, **dkw).call(f, *args, **kw)
        return wrapped_f

    def wrap_simple(f):
        def wrapped_f(*args, **kw):
            return Retrying().call(f, *args, **kw)
        return wrapped_f

    # support both @retry and @retry() as valid syntax
    if len(dargs) == 1 and callable(dargs[0]):
        return wrap_simple(dargs[0])
    else:
        return wrap


class Retrying:

    def __init__(self,
                 stop='never_stop',
                 stop_max_attempt_number=5,
                 stop_max_delay=100,
                 wait='no_sleep',
                 wait_fixed=1000,
                 wait_random_min=0, wait_random_max=1000,
                 wait_incrementing_start=0, wait_incrementing_increment=100,
                 wait_exponential_multiplier=1, wait_exponential_max=MAX_WAIT,
                 retry_on_exception=None,
                 retry_on_result=None,
                 wrap_exception=False):

        # TODO add chaining of stop behaviors
        # stop behavior
        self.stop = getattr(self, stop)
        self._stop_max_attempt_number = stop_max_attempt_number
        self._stop_max_delay = stop_max_delay

        # TODO add chaining of wait behaviors
        # wait behavior
        self.wait = getattr(self, wait)
        self._wait_fixed = wait_fixed
        self._wait_random_min = wait_random_min
        self._wait_random_max = wait_random_max
        self._wait_incrementing_start = wait_incrementing_start
        self._wait_incrementing_increment = wait_incrementing_increment
        self._wait_exponential_multiplier = wait_exponential_multiplier
        self._wait_exponential_max = wait_exponential_max

        # retry on exception filter
        if retry_on_exception is None:
            self._retry_on_exception = self.always_reject
        else:
            self._retry_on_exception = retry_on_exception

        # TODO simplify retrying by Exception types
        # retry on result filter
        if retry_on_result is None:
            self._retry_on_result = self.never_reject
        else:
            self._retry_on_result = retry_on_result

        self._wrap_exception = wrap_exception

    def never_stop(self, previous_attempt_number, delay_since_first_attempt_ms):
        """Never stop retrying."""
        return False

    def stop_after_attempt(self, previous_attempt_number, delay_since_first_attempt_ms):
        """Stop after the previous attempt >= stop_max_attempt_number."""
        return previous_attempt_number >= self._stop_max_attempt_number

    def stop_after_delay(self, previous_attempt_number, delay_since_first_attempt_ms):
        """Stop after the time from the first attempt >= stop_max_delay."""
        return delay_since_first_attempt_ms >= self._stop_max_delay

    def no_sleep(self, previous_attempt_number, delay_since_first_attempt_ms):
        """Don't sleep at all before retrying."""
        return 0

    def fixed_sleep(self, previous_attempt_number, delay_since_first_attempt_ms):
        """Sleep a fixed amount of time between each retry."""
        return self._wait_fixed

    def random_sleep(self, previous_attempt_number, delay_since_first_attempt_ms):
        """Sleep a random amount of time between wait_random_min and wait_random_max"""
        return random.randint(self._wait_random_min, self._wait_random_max)

    def incrementing_sleep(self, previous_attempt_number, delay_since_first_attempt_ms):
        """
        Sleep an incremental amount of time after each attempt, starting at
        wait_incrementing_start and incrementing by wait_incrementing_increment
        """
        result = self._wait_incrementing_start + (self._wait_incrementing_increment * (previous_attempt_number - 1))
        if result < 0:
            result = 0
        return result

    def exponential_sleep(self, previous_attempt_number, delay_since_first_attempt_ms):
        exp = 2 ** previous_attempt_number
        result = self._wait_exponential_multiplier * exp
        if result > self._wait_exponential_max:
            result = self._wait_exponential_max
        if result < 0:
            result = 0
        return result

    def never_reject(self, result):
        return False

    def always_reject(self, result):
        return True

    def should_reject(self, attempt):
        reject = False
        if attempt.has_exception:
            reject |= self._retry_on_exception(attempt.value)
        else:
            reject |= self._retry_on_result(attempt.value)

        return reject

    def call(self, fn, *args, **kwargs):
        start_time = int(round(time.time() * 1000))
        attempt_number = 1
        while True:
            try:
                attempt = Attempt(fn(*args, **kwargs), attempt_number, False)
            except BaseException as e:
                attempt = Attempt(e, attempt_number, True)

            if not self.should_reject(attempt):
                return attempt.get(self._wrap_exception)

            delay_since_first_attempt_ms = int(round(time.time() * 1000)) - start_time
            if self.stop(attempt_number, delay_since_first_attempt_ms):
                raise RetryError(attempt)
            else:
                sleep = self.wait(attempt_number, delay_since_first_attempt_ms)
                time.sleep(sleep / 1000.0)

            attempt_number += 1

class Attempt:
    """
    An Attempt encapsulates a call to a target function that may end as a
    normal return value from the function or an Exception depending on what
    occurred during the execution.
    """

    def __init__(self, value, attempt_number, has_exception):
        self.value = value
        self.attempt_number = attempt_number
        self.has_exception = has_exception

    def get(self, wrap_exception=False):
        """
        Return the return value of this Attempt instance or raise an Exception.
        If wrap_exception is true, this Attempt is wrapped inside of a
        RetryError before being raised.
        """
        if self.has_exception:
            if wrap_exception:
                raise RetryError(self)
            else:
                raise self.value
        else:
            return self.value

class RetryError(Exception):
    """
    A RetryError encapsulates the last Attempt instance right before giving up.
    """

    def __init__(self, last_attempt):
        self.last_attempt = last_attempt

    def __str__(self):
        return "Last attempt: %s" % str(self.last_attempt)
