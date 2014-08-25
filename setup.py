#!/usr/bin/env python

import os
import sys

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

settings = dict()

# Publish Helper.
if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    sys.exit()

CLASSIFIERS = [
    'Intended Audience :: Developers',
    'Natural Language :: English',
    'License :: OSI Approved :: Apache Software License',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2.6',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3.2',
    'Programming Language :: Python :: 3.3',
    'Programming Language :: Python :: 3.4',
    'Topic :: Internet',
    'Topic :: Utilities',
]

settings.update(
    name='retrying',
    version='1.2.3',
    description='Retrying',
    long_description=open('README.rst').read() + '\n\n' +
                     open('HISTORY.rst').read(),
    author='Ray Holder',
    license='Apache 2.0',
    url='https://github.com/rholder/retrying',
    classifiers=CLASSIFIERS,
    keywords="decorator decorators retry retrying exception exponential backoff",
    py_modules= ['retrying'],
    test_suite="test_retrying",
)


setup(**settings)
