#!/usr/bin/env python

from setuptools import setup

setup(
    name='tbx2cmake',
    packages=[],
    version='0.1.0',
    description='Converts a TBX SCons-based build to CMake',
    entry_points = {
        'console_scripts': ['tbx2depfile=tbx2cmake.read_scons:main'],
    }
)
