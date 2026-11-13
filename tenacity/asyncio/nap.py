# Copyright 2016 Étienne Bersac
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

import sys
import typing as t


def sleep(seconds: float) -> t.Awaitable[None]:
    """
    Sleep strategy that delays execution for a given number of seconds.

    This is the default strategy for async code
    and uses either ``trio`` or ``asyncio`` depending on availability.

    It may be mocked out for unit testing.

    For example::

        with mock.patch("tenacity.asyncio.nap.sleep"):
            ...
    """
    # If trio is already imported, then importing it is cheap.
    # If trio isn't already imported, then it's definitely not running, so we
    # can skip further checks.
    if "trio" in sys.modules:
        # If trio is available, then sniffio is too
        import sniffio
        import trio

        if sniffio.current_async_library() == "trio":
            return trio.sleep(seconds)  # noqa: ASYNC105
    # Otherwise, assume asyncio
    # Lazy import asyncio as it's expensive (responsible for 25-50% of total import overhead).
    import asyncio

    return asyncio.sleep(seconds)
