# coding: utf-8

"""
Converts a TBX-distribution into a set of CMake scripts.

No root CMakeLists.txt will be created. Instead, an autogen-CMakeLists.txt
file will be created in the root directory that can be included by the root
CMakeLists.txt. Writing of this root may be added later.

Usage: tbx2cmake <module_dir> <output_dir>
"""

import sys
import os
import logging

from docopt import docopt

from .read_scons import read_distribution

logger = logging.getLogger()



def main():
  logging.basicConfig(level=logging.INFO)

  options = docopt(__doc__)
  
  # Validate the input values
  if not os.path.isdir(options["<module_dir>"]):
    print("Error: Module path {} must be a directory".format(options["<module_dir>"]))
    sys.exit(1)
  if os.path.isfile(options["<output_dir>"]):
    print("Error: Output path {} is a file. Please specify a directory or name of one to create.".format(options["<module_dir>"]))
    sys.exit(1)

  logger.info("Reading TBX distribution")
  tbx = read_distribution(options["<module_dir>"])

  logger.info("Read {} targets in {} modules".format(len(tbx.targets), len(tbx.modules)))

if __name__ == "__main__":
  sys.exit(main())