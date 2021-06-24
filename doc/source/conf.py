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

import os
import sys

master_doc = "index"
project = "Tenacity"

# Add tenacity to the path, so sphinx can find the functions for autodoc.
sys.path.insert(0, os.path.abspath("../.."))

extensions = [
    "sphinx.ext.doctest",
    "sphinx.ext.autodoc",
    "reno.sphinxext",
]

# -- Options for sphinx.ext.doctest  -----------------------------------------

# doctest_default_flags =
cwd = os.path.abspath(os.path.dirname(__file__))
tenacity_path = os.path.join(cwd, os.pardir, os.pardir)
doctest_path = [tenacity_path]
# doctest_global_setup =
# doctest_global_cleanup =
# doctest_test_doctest_blocks =
