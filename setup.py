#!/usr/bin/env python
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import shutil
import sys

import setuptools


# Useful for very coarse version differentiation.
PY2 = sys.version_info[0] == 2
# files that can only be compiled with Python 3
PY3_FILES_PATH = ['tenacity/async.py', 'tenacity/tests/test_async.py']
if PY2:
    for fn in PY3_FILES_PATH:
        print(os.listdir(os.getcwd()))
        if os.path.isfile(fn):
            shutil.move(fn, '%s.null' % fn)

setuptools.setup(
    setup_requires=['pbr'],
    pbr=True)
