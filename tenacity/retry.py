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

import abc

import six


@six.add_metaclass(abc.ABCMeta)
class retry_base(object):
    """Abstract base class for retry strategies."""

    @abc.abstractmethod
    def __call__(self, attempt):
        pass

    def __and__(self, other):
        return retry_all(self, other)

    def __or__(self, other):
        return retry_any(self, other)


class _retry_never(retry_base):
    """Retry strategy that never rejects any result."""

    def __call__(self, attempt):
        return False


retry_never = _retry_never()


class _retry_always(retry_base):
    """Retry strategy that always rejects any result."""

    def __call__(self, attempt):
        return True


retry_always = _retry_always()


class retry_if_exception(retry_base):
    """Retry strategy that retries if an exception verifies a predicate."""

    def __init__(self, predicate):
        self.predicate = predicate

    def __call__(self, attempt):
        if attempt.failed:
            return self.predicate(attempt.exception())


class retry_if_exception_type(retry_if_exception):
    """Retries if an exception has been raised of one or more types."""

    def __init__(self, exception_types=Exception):
        self.exception_types = exception_types
        super(retry_if_exception_type, self).__init__(
            lambda e: isinstance(e, exception_types))


class retry_unless_exception_type(retry_if_exception):
    """Retries until an exception is raised of one or more types."""

    def __init__(self, exception_types=Exception):
        self.exception_types = exception_types
        super(retry_unless_exception_type, self).__init__(
            lambda e: not isinstance(e, exception_types))

    def __call__(self, attempt):
        # always retry if no exception was raised
        if not attempt.failed:
            return True
        return self.predicate(attempt.exception())


class retry_if_result(retry_base):
    """Retries if the result verifies a predicate."""

    def __init__(self, predicate):
        self.predicate = predicate

    def __call__(self, attempt):
        if not attempt.failed:
            return self.predicate(attempt.result())


class retry_if_not_result(retry_base):
    """Retries if the result refutes a predicate."""

    def __init__(self, predicate):
        self.predicate = predicate

    def __call__(self, attempt):
        if not attempt.failed:
            return not self.predicate(attempt.result())


class retry_any(retry_base):
    """Retries if any of the retries condition is valid."""

    def __init__(self, *retries):
        self.retries = retries

    def __call__(self, attempt):
        return any(map(lambda x: x(attempt), self.retries))


class retry_all(retry_base):
    """Retries if all the retries condition are valid."""

    def __init__(self, *retries):
        self.retries = retries

    def __call__(self, attempt):
        return all(map(lambda x: x(attempt), self.retries))
