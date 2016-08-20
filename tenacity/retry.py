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


def retry_never(attempt):
    """Retry strategy that never rejects any result."""
    return False


def retry_always(attempt):
    """Retry strategy that always rejects any result."""
    return True


class retry_if_exception(object):
    """Retry strategy that retries if an exception verifies a predicate."""

    def __init__(self, predicate):
        self.predicate = predicate

    def __call__(self, attempt):
        if attempt.failed:
            return self.predicate(attempt.exception())


class retry_if_exception_type(retry_if_exception):
    """Retries if an exception has been raised of a certain type."""

    def __init__(self, exception_types=Exception):
        self.exception_types = exception_types
        super(retry_if_exception_type, self).__init__(
            lambda e: isinstance(e, exception_types))


class retry_if_result(object):
    """Retries if the result verifies a predicate."""

    def __init__(self, predicate):
        self.predicate = predicate

    def __call__(self, attempt):
        if not attempt.failed:
            return self.predicate(attempt.result())


class retry_any(object):
    """Retries if any of the retries condition is valid."""

    def __init__(self, *retries):
        self.retries = retries

    def __call__(self, attempt):
        return any(map(lambda x: x(attempt), self.retries))
