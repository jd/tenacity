.. :changelog:

History
-------
1.3.3 (2014-12-14)
++++++++++++++++++
- Add minimum six version of 1.7.0 since anything less will break things

1.3.2 (2014-11-09)
++++++++++++++++++
- Ensure we wrap the decorated functions to prevent information loss
- Allow a jitter value to be passed in

1.3.1 (2014-09-30)
++++++++++++++++++
- Add requirements.txt to MANIFEST.in to fix pip installs

1.3.0 (2014-09-30)
++++++++++++++++++
- Add upstream six dependency, remove embedded six functionality

1.2.3 (2014-08-25)
++++++++++++++++++
- Add support for custom wait and stop functions

1.2.2 (2014-06-20)
++++++++++++++++++
- Bug fix to not raise a RetryError on failure when exceptions aren't being wrapped

1.2.1 (2014-05-05)
++++++++++++++++++
- Bug fix for explicitly passing in a wait type

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
