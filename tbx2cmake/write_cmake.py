# coding: utf-8

"""
Converts a TBX-distribution into a set of CMake scripts.

No root CMakeLists.txt will be created. Instead, an autogen-CMakeLists.txt
file will be created in the root directory that can be included by the root
CMakeLists.txt. Writing of this root may be added later.

Usage: tbx2cmake <module_dir> <autogen.yaml> <output_dir>
"""

import sys
import os
import logging

from docopt import docopt
import yaml

from .utils import fully_split_path 
from .read_scons import read_distribution
from .sconsemu import Target

logger = logging.getLogger()

class CMakeLists(object):
  "Represents a single CMakeLists file. Keeps track of subdirectories."
  
  def __init__(self, path="", parent=None):
    self.path = path
    self.subdirectories = {}
    self.parent = parent

    self.is_module_root = False
    self.targets = []
    self._module = None

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
    print(line.ljust(25-len(self.path)))# + " ({} targets)".format(len(self.targets)))
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

  @property
  def module(self):
    if self._module:
      return self._module
    elif self.parent:
      return self.parent.module
    else:
      return None

  def __repr__(self):
    return "<CMakeLists {}>".format(self.full_path)

  def generate_cmakelist(self):
    blocks = []

    if self.is_module_root:
      blocks.append(CMLModuleRootBlock(self))

    if self.targets:
      for target in self.targets:
        if target.name == self.module.name:
          # Handled separately
          continue
        if target.type in {Target.Type.SHARED, Target.Type.STATIC, Target.Type.MODULE}:
          blocks.append(CMLLibraryOutput(target))
        else:
          print("Not handling {} yet".format(target.type))

    if self.subdirectories:
      blocks.append(CMLSubDirBlock(self))

    return "\n\n".join(str(x) for x in blocks)

class CMakeListBlock(object):
  def __init__(self, cmakelist):
    self.cml = cmakelist

class CMLSubDirBlock(CMakeListBlock):
  def __str__(self):
    lines = []
    for subdir in sorted(self.cml.subdirectories):
      lines.append("add_subdirectory({})".format(subdir))
    return "\n".join(lines)

class CMLModuleRootBlock(CMakeListBlock):
  def __str__(self):
    lines = []
    lines.append("project({})".format(self.cml.module.name))
    lines.append("")

    # Decide what kind of library we are
    module_target = [x for x in self.cml.targets if x.name == self.cml.module.name]
    assert len(module_target) <= 1
    if module_target:
      # We are a real, compiled library
      lines.append(str(CMLLibraryOutput(module_target[0])))
    else:
      # We're just an interface library
      lines.append("add_library( {} INTERFACE )".format(self.cml.module.name))

    return "\n".join(lines)

class CMLLibraryOutput(CMakeListBlock):
  def __init__(self, target):
    self.target = target

  @property
  def typename(self):
    if self.target.type == self.target.Type.MODULE:
      return "MODULE"
    elif self.target.type == self.target.Type.SHARED:
      return "SHARED"
    elif self.target.type == self.target.Type.STATIC:
      return "SHARED"

  @property
  def is_python_module(self):
    return self.target.type == Target.Type.MODULE and "boost_python" in self.target.extra_libs

  def __str__(self):
    # if self.target.name == "cctbx_array_family_flex_ext":
    #   import pdb
    #   pdb.set_trace()

    if self.is_python_module:
      add_command = "add_python_library( {} "
    else:
      add_command = "add_library( {} {} "

    add_lib = add_command.format(self.target.name, self.typename)

    # Split sources into fixed and generated
    fixed_sources = self.target.sources
    gen_sources = []

    lines = []
    if len(add_lib + " ".join(fixed_sources)) + 2 <= 78:
      lines.append(add_lib + " ".join(fixed_sources) + " )")
    else:
      lines.append(add_lib)
      lines.extend(["    " + x for x in fixed_sources])
      lines.append(")")

    assert self.target.name == self.target.filename

    extra_libs = self.target.extra_libs
    if self.is_python_module:
      extra_libs = extra_libs - {"boost_python"}
    if extra_libs:
      lines.append("target_link_libraries( {} {} )".format(self.target.name, " ".join(extra_libs)))

    return "\n".join(lines)

def read_autogen_information(filename, tbx):
  with open(filename) as f:
    data = yaml.load(f)

  # Load the list of module-refresh-generated files
  for modname, value in data.get("libtbx_refresh", {}).items():
    module = tbx.modules[modname]
    module.generated_sources.extend(value)

  # Add the generated sources information
  tbx.other_generated = data.get("other_generated", [])

  # Find all targets that use repository-lookup sources
  for target in tbx.targets:
    lookup_sources = [x for x in target.sources if x.startswith("#")]
    unknown = set()
    for source in lookup_sources:
      # If the source is generated, then mark it so and it'll be read from the build dir
      if source[1:] in tbx.all_generated:
        target.sources.remove(source)
        target.generated_sources.add(source[1:])
      else:
        # This might be a general-lookup source. Find the actual directory.
        repositories = ["", "cctbx_project"]
        for repo in repositories:
          full_path = os.path.join(tbx.module_path, repo, source[1:])
          if os.path.isfile(full_path):
            # print("Found {} in {}".format(source, repo))
            # Change the sources list to use a relative reference to the target path
            target.sources.remove(source)
            relpath = os.path.relpath(os.path.join(repo, source[1:]), target.origin_path)
            # print("  rewriting to {}".format(relpath))
            break
        # Did we find?
        if source in target.sources:
          unknown.add(source)

    if unknown:
      print("Unknown {} from {}: {}".format(target.name, target.origin_path, unknown))

  # Double-check that we have no unknown lookup sources
  assert not unknown, "Unknown scons-repository sources: {}".format(unknown)

def main():
  logging.basicConfig(level=logging.INFO)

  options = docopt(__doc__)
  module_dir = options["<module_dir>"]
  output_dir = options["<output_dir>"]
  autogen_file = options["<autogen.yaml>"]
    
  # Validate the input values
  if not os.path.isdir(module_dir):
    print("Error: Module path {} must be a directory".format(module_dir))
    sys.exit(1)
  if os.path.isfile(output_dir):
    print("Error: Output path {} is a file. Please specify a directory or name of one to create.".format(options["<module_dir>"]))
    sys.exit(1)

  logger.info("Reading TBX distribution")
  tbx = read_distribution(module_dir)
  read_autogen_information(autogen_file, tbx)

  logger.info("Read {} targets in {} modules".format(len(tbx.targets), len(tbx.modules)))

  # Start building the CMakeLists structure
  root = CMakeLists()

  for module in tbx.modules.values():
    modroot = root.get_path(module.path)
    modroot.is_module_root = True
    modroot._module = module

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