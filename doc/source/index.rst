Tenacity
========
.. image:: https://img.shields.io/pypi/v/tenacity.svg
    :target: https://pypi.python.org/pypi/tenacity

.. image:: https://img.shields.io/travis/jd/tenacity.svg
    :target: https://travis-ci.org/jd/tenacity

.. image:: https://img.shields.io/badge/SayThanks.io-%E2%98%BC-1EAEDB.svg
    :target: https://saythanks.io/to/jd

Tenacity is an Apache 2.0 licensed general-purpose retrying library, written in
Python, to simplify the task of adding retry behavior to just about anything.
It originates from `a fork of retrying
<https://github.com/rholder/retrying/issues/65>`_.

The simplest use case is retrying a flaky function whenever an `Exception`
occurs until a value is returned.

.. testcode::

    import random
    from tenacity import retry

    @retry
    def do_something_unreliable():
        if random.randint(0, 10) > 1:
            raise IOError("Broken sauce, everything is hosed!!!111one")
        else:
            return "Awesome sauce!"

    print(do_something_unreliable())

.. testoutput::
   :hide:

   Awesome sauce!

Features
--------

- Generic Decorator API
- Specify stop condition (i.e. limit by number of attempts)
- Specify wait condition (i.e. exponential backoff sleeping between attempts)
- Customize retrying on Exceptions
- Customize retrying on expected returned result
- Retry on coroutines


Installation
------------

To install *tenacity*, simply:

.. code-block:: bash

    $ pip install tenacity


Examples
----------

.. testsetup:: *

    import logging
    from tenacity import *

    class MyException(Exception):
        pass

As you saw above, the default behavior is to retry forever without waiting when
an exception is raised.

.. testcode::

    @retry
    def never_give_up_never_surrender():
        print("Retry forever ignoring Exceptions, don't wait between retries")
        raise Exception

Let's be a little less persistent and set some boundaries, such as the number
of attempts before giving up.

.. testcode::

    @retry(stop=stop_after_attempt(7))
    def stop_after_7_attempts():
        print("Stopping after 7 attempts")
        raise Exception

We don't have all day, so let's set a boundary for how long we should be
retrying stuff.

.. testcode::

    @retry(stop=stop_after_delay(10))
    def stop_after_10_s():
        print("Stopping after 10 seconds")
        raise Exception

You can combine several stop conditions by using the `|` operator:

.. testcode::

    @retry(stop=(stop_after_delay(10) | stop_after_attempt(5)))
    def stop_after_10_s_or_5_retries():
        print("Stopping after 10 seconds or 5 retries")
        raise Exception

Most things don't like to be polled as fast as possible, so let's just wait 2
seconds between retries.

.. testcode::

    @retry(wait=wait_fixed(2))
    def wait_2_s():
        print("Wait 2 second between retries")
        raise Exception

Some things perform best with a bit of randomness injected.

.. testcode::

    @retry(wait=wait_random(min=1, max=2))
    def wait_random_1_to_2_s():
        print("Randomly wait 1 to 2 seconds between retries")
        raise Exception

Then again, it's hard to beat exponential backoff when retrying distributed
services and other remote endpoints.

.. testcode::

    @retry(wait=wait_exponential(multiplier=1, max=10))
    def wait_exponential_1():
        print("Wait 2^x * 1 second between each retry, up to 10 seconds, then 10 seconds afterwards")
        raise Exception


Then again, it's also hard to beat combining fixed waits and jitter (to
help avoid thundering herds) when retrying distributed services and other
remote endpoints.

.. testcode::

    @retry(wait=wait_fixed(3) + wait_random(0, 2))
    def wait_fixed_jitter():
        print("Wait at least 3 seconds, and add up to 2 seconds of random delay")
        raise Exception

When multiple processes are in contention for a shared resource, exponentially
increasing jitter helps minimise collisions.

.. testcode::

    @retry(wait=wait_random_exponential(multiplier=1, max=60))
    def wait_exponential_jitter():
        print("Randomly wait up to 2^x * 1 seconds between each retry until the range reaches 60 seconds, then randomly up to 60 seconds afterwards")
        raise Exception


Sometimes it's necessary to build a chain of backoffs.

.. testcode::

    @retry(wait=wait_chain(*[wait_fixed(3) for i in range(3)] +
                           [wait_fixed(7) for i in range(2)] +
                           [wait_fixed(9)]))
    def wait_fixed_chained():
        print("Wait 3s for 3 attempts, 7s for the next 2 attempts and 9s for all attempts thereafter")
        raise Exception

We have a few options for dealing with retries that raise specific or general
exceptions, as in the cases here.

.. testcode::

    @retry(retry=retry_if_exception_type(IOError))
    def might_io_error():
        print("Retry forever with no wait if an IOError occurs, raise any other errors")
        raise Exception

We can also use the result of the function to alter the behavior of retrying.

.. testcode::

    def is_none_p(value):
        """Return True if value is None"""
        return value is None

    @retry(retry=retry_if_result(is_none_p))
    def might_return_none():
        print("Retry with no wait if return value is None")

We can also combine several conditions:

.. testcode::

    def is_none_p(value):
        """Return True if value is None"""
        return value is None

    @retry(retry=(retry_if_result(is_none_p) | retry_if_exception_type()))
    def might_return_none():
        print("Retry forever ignoring Exceptions with no wait if return value is None")

Any combination of stop, wait, etc. is also supported to give you the freedom
to mix and match.

It's also possible to retry explicitly at any time by raising the `TryAgain`
exception:

.. testcode::

   @retry
   def do_something():
       result = something_else()
       if result == 23:
          raise TryAgain

While callables that "timeout" retrying raise a `RetryError` by default,
we can reraise the last attempt's exception if needed:

.. testcode::

    @retry(reraise=True, stop=stop_after_attempt(3))
    def raise_my_exception():
        raise MyException("Fail")

    try:
        raise_my_exception()
    except MyException:
        # timed out retrying
        pass

It's possible to execute an action before any attempt of calling the function
by using the before callback function:

.. testcode::

    logger = logging.getLogger(__name__)

    @retry(stop=stop_after_attempt(3), before=before_log(logger, logging.DEBUG))
    def raise_my_exception():
        raise MyException("Fail")

In the same spirit, It's possible to execute after a call that failed:

.. testcode::

    logger = logging.getLogger(__name__)

    @retry(stop=stop_after_attempt(3), after=after_log(logger, logging.DEBUG))
    def raise_my_exception():
        raise MyException("Fail")

You can access the statistics about the retry made over a function by using the
`retry` attribute attached to the function and its `statistics` attribute:

.. testcode::

    @retry(stop=stop_after_attempt(3))
    def raise_my_exception():
        raise MyException("Fail")

    try:
        raise_my_exception()
    except Exception:
        pass

    print(raise_my_exception.retry.statistics)

.. testoutput::
   :hide:

   ...

You can change the arguments of a retry decorator as needed when calling it by
using the `retry_with` function attached to the wrapped function:

.. testcode::

    @retry(stop=stop_after_attempt(3))
    def raise_my_exception():
        raise MyException("Fail")

    try:
        raise_my_exception.retry_with(stop=stop_after_attempt(4))()
    except Exception:
        pass

    print(raise_my_exception.retry.statistics)

.. testoutput::
   :hide:

   ...

Finally, ``retry`` works also on asyncio and Tornado coroutines. Sleeps are done
asynchronously too.

.. code-block:: python

    @retry
    async def my_async_function(loop):
        await loop.getaddrinfo('8.8.8.8', 53)

.. code-block:: python

    @retry
    @tornado.gen.coroutine
    def my_async_function(http_client, url):
        yield http_client.fetch(url)

Contribute
----------

#. Check for open issues or open a fresh issue to start a discussion around a
   feature idea or a bug.
#. Fork `the repository`_ on GitHub to start making your changes to the
   **master** branch (or branch off of it).
#. Write a test which shows that the bug was fixed or that the feature works as
   expected.
#. Make the docs better (or more detailed, or more easier to read, or ...)

.. _`the repository`: https://github.com/jd/tenacity

