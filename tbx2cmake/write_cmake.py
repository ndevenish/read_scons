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

from .utils import fully_split_path 
from .read_scons import read_distribution

logger = logging.getLogger()

class CMakeLists(object):
  "Represents a single CMakeLists file. Keeps track of subdirectories."
  
  def __init__(self, path="", parent=None):
    self.path = path
    self.subdirectories = {}
    self.parent = parent

    self.is_module_root = False

  def get_path(self, path):
    "Returns a CMakeLists object for a specific subpath"
    assert not os.path.isabs(path)
    parts = fully_split_path(path)
    assert not ".." in parts, "No relative referencing implemented"
    if parts[0] in {"", "."}:
      return self
    else:
      if not parts[0] in self.subdirectories:
        subdir = CMakeLists(parts[0], parent=self)
        self.subdirectories[parts[0]] = subdir
      else:
        subdir = self.subdirectories[parts[0]]
      if len(parts) > 1:
        return subdir.get_path(os.path.join(*parts[1:]))
      else:
        return subdir


  def draw_tree(self, indent="", last=True, root=True):
    "Quick and easy function to dump a tree representation"""
    line = indent
    if not root:
      if last:
        line += " └"
        indent += "  "
      else:
        line += " ├"
        indent += " │"
    if not self.parent:
      line += " ROOT"
    else:
      line += " " + self.path
    print(line)
    for i, child in enumerate(sorted(self.subdirectories.values(), key=lambda x: x.path)):
      child.draw_tree(indent, i == len(self.subdirectories) - 1, root=False)

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

  # Start building the CMakeLists structure
  root = CMakeLists()

  for module in tbx.modules.values():
    # import pdb
    # pdb.set_trace()
    # root.get_path('cctbx_project/chiltbx')
    modroot = root.get_path(module.path)
    modroot.is_module_root = True

  import pdb
  pdb.set_trace()

if __name__ == "__main__":
  sys.exit(main())