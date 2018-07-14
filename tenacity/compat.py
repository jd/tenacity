"""Utilities for providing backward compatibility."""

import six
from tenacity import _utils
import inspect

from fractions import Fraction


def func_takes_retry_state(func):
    if not six.callable(func):
        return False
    if not inspect.isfunction(func):
        # func is a callable object rather than a function
        func = func.__call__
    func_spec = _utils.getargspec(func)
    return 'retry_state' in func_spec.args


_unset = object()


def make_wait_retry_state(previous_attempt_number, delay_since_first_attempt,
                          last_result=None):
    required_parameter_unset = (previous_attempt_number is _unset or
                                delay_since_first_attempt is _unset)
    if required_parameter_unset:
        missing = []
        if previous_attempt_number is _unset:
            missing.append('previous_attempt_number')
        if delay_since_first_attempt is _unset:
            missing.append('delay_since_first_attempt')
        missing_str = ', '.join(repr(s) for s in missing)
        raise TypeError('wait func missing parameters: ' + missing_str)

    from tenacity import RetryCallState
    retry_state = RetryCallState(None, None, (), {})
    retry_state.attempt_number = previous_attempt_number
    if last_result is not None:
        retry_state.outcome = last_result
    else:
        retry_state.set_result(None)
    # Ensure outcome_timestamp - start_time is *exactly* equal to the delay to
    # avoid complexity in test code.
    retry_state.start_time = Fraction(retry_state.start_time)
    retry_state.outcome_timestamp = (
        retry_state.start_time + Fraction(delay_since_first_attempt))
    assert retry_state.seconds_since_start == delay_since_first_attempt
    return retry_state


def wait_dunder_call_accept_old_params(fn):
    """Wrap wait fn taking "retry_state" to accept old parameter tuple.

    This is a backward compatibility shim to ensure tests keep working.
    """
    @six.wraps(fn)
    def new_fn(self,
               previous_attempt_number=_unset,
               delay_since_first_attempt=_unset,
               last_result=None,
               retry_state=None):
        if retry_state is None:
            retry_state = make_wait_retry_state(
                previous_attempt_number=previous_attempt_number,
                delay_since_first_attempt=delay_since_first_attempt,
                last_result=last_result)
        return fn(self, retry_state=retry_state)
    return new_fn


def func_takes_last_result(waiter):
    """Check if function has a "last_result" parameter.

    Needed to provide backward compatibility for wait functions that didn't
    take "last_result" in the beginning.
    """
    if not six.callable(waiter):
        return False
    if not inspect.isfunction(waiter):
        # waiter is a class, check dunder-call rather than dunder-init.
        waiter = waiter.__call__
    waiter_spec = _utils.getargspec(waiter)
    return 'last_result' in waiter_spec.args


def wait_func_accept_retry_state(wait_func):
    """Wrap wait function to accept "retry_state" parameter."""
    if not six.callable(wait_func):
        return wait_func

    takes_retry_state = func_takes_retry_state(wait_func)
    if takes_retry_state:
        return wait_func

    takes_last_result = func_takes_last_result(wait_func)
    if takes_last_result:
        @six.wraps(wait_func)
        def wrapped_wait_func(retry_state):
            return wait_func(
                retry_state.attempt_number,
                retry_state.seconds_since_start,
                last_result=retry_state.outcome,
            )
    else:
        @six.wraps(wait_func)
        def wrapped_wait_func(retry_state):
            return wait_func(
                retry_state.attempt_number,
                retry_state.seconds_since_start,
            )
    return wrapped_wait_func


def before_sleep_func_accept_retry_state(fn):
    """Wrap "before_sleep" function to accept "retry_state"."""
    if not six.callable(fn):
        return fn

    takes_retry_state = func_takes_retry_state(fn)
    if takes_retry_state:
        return fn

    @six.wraps(fn)
    def wrapped_before_sleep_func(retry_state):
        # retry_object, sleep, last_result
        return fn(
            retry_state.retry_object,
            sleep=getattr(retry_state.next_action, 'sleep'),
            last_result=retry_state.outcome)
    return wrapped_before_sleep_func
