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

import six

# sys.maxint / 2, since Python 3.2 doesn't have a sys.maxint...
try:
    MAX_WAIT = sys.maxint / 2
except AttributeError:
    MAX_WAIT = 1073741823


if six.PY2:
    def capture(fut, tb):
        # TODO(harlowja): delete this in future, since its
        # has to repeatedly calculate this crap.
        fut.set_exception_info(tb[1], tb[2])
else:
    def capture(fut, tb):
        fut.set_exception(tb[1])
