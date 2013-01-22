Retrying, to retry all the things
=========================


.. image:: https://travis-ci.org/rholder/retrying.png?branch=master
        :target: https://travis-ci.org/rholder/retrying

Retrying is an Apache 2.0 licensed general-purpose retrying library, written in
Python, to simplify the task of adding retry behavior to just about anything.


The simplest use case is retrying a flaky function whenever an Exception occurs
until a value is returned.

.. code-block:: python

    import random
    from retrying import retry

    @retry
    def do_something_unreliable():
        if random.randint(0, 10) > 1:
            raise IOError("Broken sauce, everything is hosed!!!111one")
        else:
            return "Awesome sauce!"

    print do_something_unreliable()

TODO flush out more examples


Features
--------

- Generic Decorator API
- Specify stop condition (i.e. limit by number of attempts)
- Specify wait condition (i.e. exponential backoff sleeping between attempts)
- Customize retrying on Exceptions
- Customize retrying on expected returned result


Installation
------------

To install retrying, simply:

.. code-block:: bash

    $ pip install retrying

Or, if you absolutely must:

.. code-block:: bash

    $ easy_install retrying

But, you might regret that later.


Contribute
----------

#. Check for open issues or open a fresh issue to start a discussion around a feature idea or a bug.
#. Fork `the repository`_ on GitHub to start making your changes to the **master** branch (or branch off of it).
#. Write a test which shows that the bug was fixed or that the feature works as expected.
#. Send a pull request and bug the maintainer until it gets merged and published. :) Make sure to add yourself to AUTHORS_.

.. _`the repository`: http://github.com/rholder/retrying
.. _AUTHORS: https://github.com/rholder/retrying/blob/master/AUTHORS.rst
