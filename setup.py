#!/usr/bin/env python

from setuptools import setup

setup(
    name='tbx2cmake',
    packages=["tbx2cmake"],
    version='0.1.0',
    description='Converts a TBX SCons-based build to CMake',
    entry_points = {
        'console_scripts': [
          'tbx2depfile=tbx2cmake.read_scons:main',
          'tbx2cmake=tbx2cmake.write_cmake:main'
        ],
    },
    install_requires=["enum34", "docopt", "networkx"],
)
