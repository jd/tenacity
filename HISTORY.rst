.. :changelog:

History
-------

1.2.0 (2014-05-04)
++++++++++++++++++
- Remove the need for explicit specification of stop/wait types when they can be inferred
- Add a little checking for exception propagation

1.1.0 (2014-03-31)
++++++++++++++++++
- Added proper exception propagation through reraising with Python 2.6, 2.7, and 3.2 compatibility
- Update test suite for behavior changes

1.0.1 (2013-03-20)
++++++++++++++++++
- Fixed a bug where classes not extending from the Python exception hierarchy could slip through
- Update test suite for custom Python exceptions

1.0.0 (2013-01-21)
++++++++++++++++++
- First stable, tested version now exists
- Apache 2.0 license applied
- Sanitizing some setup.py and test suite running
- Added Travis CI support
