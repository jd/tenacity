===============
 API Reference
===============

Retry Main API
--------------

.. autofunction:: tenacity.retry
   :noindex:

.. autoclass:: tenacity.Retrying
   :members:

.. autoclass:: tenacity.AsyncRetrying
   :members:

.. autoclass:: tenacity.tornadoweb.TornadoRetrying
   :members:

After Functions
---------------

Those functions can be used as the `after` keyword argument of
:py:func:`tenacity.retry`.

.. automodule:: tenacity.after
   :members:

Before Functions
----------------

Those functions can be used as the `before` keyword argument of
:py:func:`tenacity.retry`.

.. automodule:: tenacity.before
   :members:

Before Sleep Functions
----------------------

Those functions can be used as the `before_sleep` keyword argument of
:py:func:`tenacity.retry`.

.. automodule:: tenacity.before_sleep
   :members:

Nap Functions
-------------

Those functions can be used as the `sleep` keyword argument of
:py:func:`tenacity.retry`.

.. automodule:: tenacity.nap
   :members:

Retry Functions
---------------

Those functions can be used as the `retry` keyword argument of
:py:func:`tenacity.retry`.

.. automodule:: tenacity.retry
   :members:

Stop Functions
--------------

Those functions can be used as the `stop` keyword argument of
:py:func:`tenacity.retry`.

.. automodule:: tenacity.stop
   :members:

Wait Functions
--------------

Those functions can be used as the `wait` keyword argument of
:py:func:`tenacity.retry`.

.. automodule:: tenacity.wait
   :members:
