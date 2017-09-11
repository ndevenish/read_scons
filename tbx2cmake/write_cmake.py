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
    self.targets = []

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
    print(line.ljust(25-len(self.path)) + " ({} targets)".format(len(self.targets)))
    for i, child in enumerate(sorted(self.subdirectories.values(), key=lambda x: x.path)):
      child.draw_tree(indent, i == len(self.subdirectories) - 1, root=False)

  def all(self):
    yield self
    for child in self.subdirectories.values():
      for result in child.all():
        yield result

  @property
  def full_path(self):
    if self.parent:
      return os.path.join(self.parent.full_path, self.path)
    else:
      return self.path

  def __repr__(self):
    return "<CMakeLists {}>".format(self.full_path)

  def generate_cmakelist(self):
    blocks = []

    if self.subdirectories:
      blocks.append(CMLSubDirBlock(self))

    return "\n\n".join(str(x) for x in blocks)

class CMakeListBlock(object):
  def __init__(self, cmakelist):
    pass

class CMLSubDirBlock(CMakeListBlock):
  def __init__(self, cmakelist):
    self.cml = cmakelist

  def __str__(self):
    lines = []
    for subdir in sorted(self.cml.subdirectories):
      lines.append("add_subdirectory({})".format(subdir))
    return "\n".join(lines)

def main():
  logging.basicConfig(level=logging.INFO)

  options = docopt(__doc__)
  module_dir = options["<module_dir>"]
  output_dir = options["<output_dir>"]
    
  # Validate the input values
  if not os.path.isdir(module_dir):
    print("Error: Module path {} must be a directory".format(module_dir))
    sys.exit(1)
  if os.path.isfile(output_dir):
    print("Error: Output path {} is a file. Please specify a directory or name of one to create.".format(options["<module_dir>"]))
    sys.exit(1)

  logger.info("Reading TBX distribution")
  tbx = read_distribution(module_dir)

  logger.info("Read {} targets in {} modules".format(len(tbx.targets), len(tbx.modules)))

  # Start building the CMakeLists structure
  root = CMakeLists()

  for module in tbx.modules.values():
    modroot = root.get_path(module.path)
    modroot.is_module_root = True

  for target in tbx.targets:
    cmakelist = root.get_path(target.origin_path)
    cmakelist.targets.append(target)

  root.draw_tree()

  # Make sure the output path exists
  if not os.path.isdir(output_dir):
    os.makedirs(output_dir)

  for cml in root.all():
    path = os.path.join(output_dir, cml.full_path)
    if not os.path.isdir(path):
      os.makedirs(path)
    filename = "CMakeLists.txt"
    if cml is root:
      filename = "autogen_CMakeLists.txt"
    with open(os.path.join(path, filename), "w") as f:
      f.write(cml.generate_cmakelist())


if __name__ == "__main__":
  sys.exit(main())