#!/usr/bin/env python
# coding: utf-8

import os
import sys
from collections import namedtuple
from types import ModuleType
import imp
from mock import Mock
import re
import inspect
import json
import glob

import networkx as nx

# class TBXModuleFinder(object):
#   ALL_POSSIBLE = {'amber_adaptbx', 'annlib', 'annlib_adaptbx', 'boost', 'boost_adaptbx', 
#                   'cbflib', 'cbflib_adaptbx', 'ccp4io', 'ccp4io_adaptbx', 'cctbx', 
#                   'chem_data', 'chiltbx', 'clipper', 'clipper_adaptbx', 'cma_es', 
#                   'cootbx', 'crys3d', 'cudatbx', 'cxi_user', 'dials', 'dials_regression', 
#                   'dox', 'dox.sphinx', 'dxtbx', 'elbow', 'fable', 'fftw3tbx', 
#                   'gltbx', 'gui_resources', 'iota', 'iotbx', 'king', 'ksdssp', 
#                   'labelit', 'libtbx', 'mmtbx', 'muscle', 'omptbx', 'opt_resources', 
#                   'phaser', 'phaser_regression', 'phenix', 'phenix_examples', 
#                   'phenix_html', 'phenix_regression', 'Plex', 'prime', 'probe', 
#                   'pulchra', 'PyQuante', 'reduce', 'reel', 'rstbx', 'scitbx', 
#                   'scons', 'simtbx', 'smtbx', 'solve_resolve', 'sphinx', 'spotfinder', 
#                   'suitename', 'tbxx', 'tntbx', 'ucif', 'wxtbx', 'xfel', 'xia2', 
#                   'xia2_regression'}

#   def __init__(self):
#     self._repositories = set()
#     add_repository("cctbx_project")

#   def add_repository(self, name):
#     """Add the name of a folder that can contain other modules"""
#     self._repositories.add(name)

#   def find(self, basepath):
#     """Find all modules from a base path. Returns a map of module name to relative path."""
#     paths = {}
#     for path, dirs, files in os.walk(basepath):
#       for entry in dirs:
#         if entry in self.ALL_POSSIBLE:

#       if path == basepath:
#         for entry in dirs:
#           if not entry in self._repositories:
#             dirs.remote(entry)
#     for subdir in next(os.walk(basepath))[1]:
#       if subdir in self.ALL_POSSIBLE:
#         paths[subdir] = 
#       is os.path.isdir(os.path.join(basepath, subdir))


def return_as_list(f):
  """Decorated a function to convert a generator to a list"""
  def _wrap(*args, **kwargs):
    return list(f(*args, **kwargs))
  return _wrap

class LibTBXModule(object):
  """Represents a libtbx module"""
  def __init__(self, name, path):
    self.name = name
    self.path = path
    self.required = set()
    # self.required_by = set()

    if self.has_config:
      # Read the configuration for a basic dependency tree
      with open(os.path.join(self.path, "libtbx_config")) as f:
        self._config = eval(f.read())
        self.required = set(self._config.get("modules_required_for_build", set()))
        self.required |= set(self._config.get("optional_modules", set()))
        # Handle aliases/multis
        if "boost" in self.required:
          self.required.add("boost_adaptbx")
          self.required.remove("boost")
        if "annlib" in self.required:
          self.required.add("annlib_adaptbx")
          self.required.remove("annlib")

  def __repr__(self):
    return "Module(name={}, path={})".format(repr(self.name), repr(self.path))
  @property
  def has_sconscript(self):
    return os.path.isfile(os.path.join(self.path, "SConscript"))
  @property
  def has_config(self):
    return os.path.isfile(os.path.join(self.path, "libtbx_config"))


@return_as_list
def find_libtbx_modules(modulepath, repositories={"cctbx_project"}):
  """Find all modules in a path"""

  # Find all direct subdirs, plus all in cctbx_project
  subdirs = [x for x in list(next(os.walk(modulepath))[1]) if not x.startswith(".")]
  for repo in repositories:
    if repo in subdirs:
      subdirs.remove(repo)
    for dirname in next(os.walk(os.path.join(modulepath, repo)))[1]:
      if not dirname.startswith("."):
        subdirs.append(os.path.join(repo, dirname))

  # All subdirs == all modules, as far as libtbx logic goes. Filter them later.
  for dirname in subdirs:
      name = os.path.basename(dirname)
      path = dirname
      yield LibTBXModule(name=name, path=path)

def new_module(name, doc=None):
  """Create a new module and inject it into sys.modules.

  :param name: Fully qualified name (including parent .)
  :returns:  A module, injected into sys.modules
  """
  m = ModuleType(name, doc)
  m.__file__ = name + '.py'
  sys.modules[name] = m
  return m

class InjectableModule(object):
  """Load and run a python script with an injected globals dictionary.
  This is to emulate what it appears libtbx/scons does to run refresh scripts
  """
  def __init__(self, module_path):
    path, module_filename = os.path.split(module_path)
    module_name, ext = os.path.splitext(module_filename)
    module = imp.new_module(module_name)
    module.__file__ = module_path
    with open(module_path) as f:
      self.bytecode = compile(f.read(), str(module_path), "exec")
    self.module = module

  def inject(self, globals):
    vars(self.module).update(globals)

  def execute(self):
    exec(self.bytecode, vars(self.module))

  def getvar(self, name):
    return getattr(self.module, name)


class SConsConfigurationContext(object):
  def __init__(self, env):
    self.env = env

  """Represents the object returned by a Scons Environment's 'Configure'"""
  def TryRun(self, code, **kwargs):
    if "__GNUC_PATCHLEVEL__" in code:
      # We are trying to extract compiler information. Just return constant.
      data = {"llvm":1, "clang":1, "clang_major":8, "clang_minor":1, 
              "clang_patchlevel":0, "GNUC":4, "GNUC_MINOR":2, 
              "GNUC_PATCHLEVEL":1, "clang_version": "8.1.0 (clang-802.0.42)", 
              "VERSION": "4.2.1 Compatible Apple LLVM 8.1.0 (clang-802.0.42)"}
      return (1, repr(data))

    # Get the name of the calling function
    caller = inspect.stack()[1][3]
    # Yes, openMP works as far as libtbx configuration is concerned
    if caller == "enable_openmp_if_possible":
      return (1,"e=2.71828, pi=3.14159")
    if caller == "write_type_id_eq_h":
      # This is what the mac returns, but we handle this already anyway
      return (1, "0010")
    # Covers both basic tests for gltbx
    if "gltbx/include_opengl.h" in code:
      return (1, "6912")

    assert False, "Unable to determine purpose of TryRun"

  def TryCompile(self, code, **kwargs):
    if code == """\
      #include <boost/thread.hpp>

      struct callable { void operator()(){} };
      void whatever() {
        callable f;
        boost::thread t(f);
      }
      """:
      return 1
    elif code == "#include <iostream>":
      return 1
    elif code == "#include <Python.h>":
      return 1
    elif code.strip() == "#include <gltbx/include_opengl.h>":
      return 1
    elif code == "#include <fftw3.h>":
      return 1

    assert False, "Not recognised TryCompile"

  def Finish(self):
    pass

class ProgramReturn(object):
  def __init__(self, path):
    self.path = path
  def get_abspath(self):
    return self.path

def _generate_sconsbaseenv(running_within):
  class _SconsEnvironment(object):
    _instances = []
    runner = running_within
    def __init__(self, *args, **kwargs):
      self._instances.append(self)
      self.parent = None
      self.args = args
      defaults = {
        "OBJSUFFIX": ".o",
        "SHLINKFLAGS": [],
        "BUILDERS": {},
        "SHLINKCOM": ["SHLINKCOMDEFAULT"],
        "LINKCOM": ["LINKCOMDEFAULT"],
        "CCFLAGS": [],
        "SHCCFLAGS": [],
        "CXXFLAGS": [],
        "SHCXXFLAGS": [],
        "PROGPREFIX": "",
        "PROGSUFFIX": "",
      }
      defaults.update(kwargs)
      self.kwargs = defaults


    def Append(self, **kwargs):
      for key, val in kwargs.items():
        if not key in self.kwargs:
          self.kwargs[key] = []
        self.kwargs[key].extend(val)

    def Prepend(self, **kwargs):
      for key, val in kwargs.items():
        if not key in self.kwargs:
          self.kwargs[key] = []
        self.kwargs[key][:0] = val

    def Replace(self, **kwargs):
      self.kwargs.update(kwargs)

    def Configure(self):
      return SConsConfigurationContext(self)

    def Clone(self, **kwargs):
      clone = type(self)()
      clone.parent = self
      clone.kwargs.update(kwargs)
      return clone

    def __setitem__(self, key, value):
      self.kwargs[key] = value

    def __getitem__(self, key):
      return self.kwargs[key]

    def SharedLibrary(self, target, source, **kwargs):
      print("Shared lib: {} (relative to {})\n     sources: {}".format(target, self.runner._current_sconscript, source))

    def StaticLibrary(self, target, source, **kwargs):
      print("Static lib: {} (relative to {})\n     sources: {}".format(target, self.runner._current_sconscript, source))

    def Program(self, target, source):
      print("Program: {} (relative to {})\n     sources: {}".format(target, self.runner._current_sconscript, source))
      # Used at least once
      return [ProgramReturn(target)]

    def cudaSharedLibrary(self, target, source):
      print("CUDA program: {}, {}".format(target, source))

    def SharedObject(self,source):
      print("Shared object: {}".format(source))
      return ["SHAREDOBJECT", source]

    def Repository(self, path):
      if path == "DISTPATH":
        return
      assert False, "Unknown Repository usage: {}".format(path)

    def SConscript(self, name, exports=None):
      self.runner.sconscript_command(name, exports)

  return _SconsEnvironment

class FakePath(object):
  pass

class UnderBuild(FakePath):
  def __init__(self, path):
    self.path = path
  def __repr__(self):
    return "UnderBuild({})".format(repr(self.path))
  def __abs__(self):
    return os.path.join("UNDERBUILD", self.path)
  # def endswith(self, text):


class UnderBase(FakePath):
  def __init__(self, path):
    self.path = path
  def __repr__(self):
    return "UnderBuild({})".format(repr(self.path))
  def find(self, substr):
    return self.path.find(substr)

# class PythonIncludePath(FakePath):
#   def split(self, *args):
#     return ["PYTHONINCLUDEPATH"]

class libtbxBuildOptions(object):
  build_boost_python_extensions = True
  scan_boost = False
  compiler = "default"
  static_exe = False
  debug_symbols = True
  force_32bit = False
  warning_level = 0
  optimization = False
  use_environment_flags = False
  enable_cxx11 = False
  enable_openmp_if_possible = True
  enable_cuda = True
  enable_boost_threads = True
  boost_python_no_py_signatures = False
  precompile_headers = False
  boost_python_bool_int_strict = True # Undocumented in boost::python and whether
                                      # anything depends on this is long lost.... but
                                      # since it's just a define keep in for parsing scons

class libtbxEnv(object):
  boost_version = 106500

  def __init__(self):
    self.build_options = libtbxBuildOptions()


  def under_build(self, path):
    return os.path.join("UNDERBUILD", path)#UnderBuild(path)

  def under_base(self, path):
    return os.path.join("BASEDIR", path)#UnderBase(path)

  def dist_path(self, path):
    return os.path.join("DISTPATH", path)

  def under_dist(self, module_name, path):
    return os.path.join("DISTPATH[{}]".format(module_name), path)
  @property
  def build_path(self):
    return "UNDERBUILD"

  @property
  def lib_path(self):
    # This returns a path object
    return UnderBuild("lib")

  def find_in_repositories(self, relative_path, **kwargs):
    return os.path.join("REPOSITORIES", relative_path)

  def has_module(self, module):
    return True

  def write_dispatcher_in_bin(self, source_file, target_file):
    print("Called to write dispatcher {} to {}".format(target_file, source_file))

class libtbxIncludeRegistry(list):
  def scan_boost(self, *args, **kwargs):
    return self
  def set_boost_dir_name(self, *args, **kwargs):
    return self
  def append(self, env, paths):
    # This function does some logic to prevent dependency scanning of boost
    # path building. Just ignore this as we are building boost externally.
    for path in paths:
      env.Append(CPPPATH=[path])
  def prepend(self, env, paths):
    # This function does some logic to prevent dependency scanning of boost
    # path building. Just ignore this as we are building boost externally.
    for path in paths:
      env.Prepend(CPPPATH=[path])


class EasyRunResult(object):
  def __init__(self, output):
    self.stdout_lines = list(output)
  def raise_if_errors(self):
    return self

class libtbxEasyRun(object):
  def fully_buffered(self, command, **kwargs):
    if command == "/usr/bin/uname -p":
      return EasyRunResult(["i386"])
    elif command == "/usr/bin/sw_vers -productVersion":
      return EasyRunResult(["10.12.0"])
    elif command == "nvcc --version":
      return EasyRunResult(["Cuda compilation tools, release 8.0, V8.0.61"])
    assert False, "No command known; {}".format(command)

class _SConsBuilder(object):
  def __init__(self, action, **kwargs):
    self.action = action
    self.kwargs = kwargs
    self.builders = []
  def add_src_builder(self, builder):
    self.builders.append(builder)

class _fakeFile(object):
  def __init__(self, filename):
    self.filename = filename
    self.data = ""

  def write(self, data):
    self.data += data

  def read(self):
    caller = inspect.stack()[1][3]
    if "csymlib.c" in self.filename or caller == "replace_printf":
      return ""


def _wrappedOpen(file, mode=None):
  return _fakeFile(file)
  # assert False, "Unknown Open; {}/{}".format(file, mode)

class SconsBuilder(object):
  def __init__(self, dist, modules):
    self._exports = {}
    self._current_sconscript = None

    self.dist_path = dist
    self.module_map = modules

  def parse_module(self, module):
    scons = os.path.join(module.path, "SConscript")
    if not os.path.isfile(scons):
      print("No Sconscript for module {}".format(module.name))
      return
    print "Parsing {}".format(module.name)  
    self.parse_sconscript(scons)

  def sconscript_command(self, name, exports=None):
    newpath = os.path.join(os.path.dirname(self._current_sconscript), name)
    print("Loading sub-sconscript {}".format(newpath))
    self.parse_sconscript(newpath, custom_exports=exports)
    print("Returning to sconscript {}".format(self._current_sconscript))

  def parse_sconscript(self, filename, custom_exports=None):
    # Build the object used to run the script
    module = InjectableModule(filename)

    # Build the Scons injection environment
    def _env_export(*args):
      print "Exporting", args
      for name in args:
        self._exports[name] = module.getvar(name)
    def _env_import(*args):
      print "Importing", args
      inj = {}
      for imp in args:
        if custom_exports and imp in custom_exports:
          inj[imp] = custom_exports[imp]
        else:
          inj[imp] = self._exports[imp]
      module.inject(inj)

    def _env_glob(path):
      globpath = os.path.join(os.path.dirname(filename), path)
      results = glob.glob(globpath)
      return results

    inj = {
      "Environment": _generate_sconsbaseenv(self),
      "open": _wrappedOpen,
      "ARGUMENTS": {},
      "Builder": _SConsBuilder,
      "Export": _env_export,
      "Import": _env_import,
      "SConscript": self.sconscript_command,
      "Glob": _env_glob,
    }
    # Inject this and execute
    module.inject(inj)
    # Handle the stack of Sconscript processing
    prev_scons = self._current_sconscript
    self._current_sconscript = filename
    module.execute()
    self._current_sconscript = prev_scons

class AttrDict(dict):
  def __init__(self, *args, **kwargs):
    super(AttrDict, self).__init__(*args, **kwargs)
    self.__dict__ = self

# Create the libtbx environment
libtbx = new_module("libtbx")
libtbx.load_env = new_module("libtbx.load_env")
libtbx.env_config = new_module("libtbx.env_config")
libtbx.utils = new_module("libtbx.utils")
libtbx.str_utils = new_module("libtbx.str_utils")
libtbx.path = new_module("libtbx.path")
# open(libtbx.env.under_build("include_paths"), "w")

# Functions
def _fail(*args, **kwargs):
  raise NotImplementedError("Not Implemented")
def _wtf(*args, **kwargs):
  assert False, "WTF? {}, {}".format(args, kwargs)
def _unique_paths(paths):
  return list(set(paths))
# def _tbx_norm_join(a, b):
#   return 
libtbx.easy_run = libtbxEasyRun()
libtbx.utils.getenv_bool = _fail
libtbx.str_utils.show_string = _fail
libtbx.path.norm_join = lambda a,b: os.path.normpath(os.path.join(a,b))
libtbx.path.full_command_path = _fail
libtbx.group_args = AttrDict
libtbx.env_config.include_registry = libtbxIncludeRegistry
libtbx.env_config.is_64bit_architecture = lambda: True
libtbx.env_config.python_include_path = lambda: "PYTHON/INCLUDE/PATH"
libtbx.env_config.unique_paths = _unique_paths

# Too complex to try shortcutting; just fall through where used
def _libtbx_select_matching(key, choices, default=None):
  for key_pattern, value in choices:
    m = re.search(key_pattern, key)
    if m is not None: return value
  return default
libtbx.utils.select_matching = _libtbx_select_matching
libtbx.utils.warn_if_unexpected_md5_hexdigest = Mock()
libtbx.utils.write_this_is_auto_generated =  Mock()

def _tbx_darwin_shlinkcom(env_etc, env, lo, dylib):
  "Very vague ideas about what this is any why it's used"
  if "libboost_thread.lo" in lo:
    return
  if "libboost_python.lo" in lo:
    return
  _wtf(env_etc, env, lo, dylib)

libtbx.env_config.darwin_shlinkcom = _tbx_darwin_shlinkcom

libtbx.env = libtbxEnv()
libtbx.manual_date_stamp = 20090819 # I don't even

# data module used during it's sconscript
fftw3tbx = new_module("fftw3tbx")
fftw3tbx.fftw3_h = "fftw3.h"

# Fake anything SCons that we interact with
SCons = new_module("SCons")
SCons.Action = new_module("SCons.Action")
SCons.Scanner = new_module("SCons.Scanner")
SCons.Scanner.C = new_module("SCons.Scanner.C")

SCons.Action.FunctionAction = Mock()
SCons.Scanner.C.CScanner = Mock()

if __name__ == "__main__":
  MODULE_PATH = "."
  modules = find_libtbx_modules(MODULE_PATH)

  # Make a lookup to find modules by name
  modulemap = {x.name: x for x in modules}

  G = nx.DiGraph()
  G.add_nodes_from(modulemap.keys())

  # Build the dependency graph from the libtbx information
  for module in modules:
    # modulemap[module.name] = module

    # G.add_node(module.name)
    for req in module.required:
      G.add_edge(module.name, req)
    
    # Force a dependency on libtbx so it goes before everything else
    if not module.name == "libtbx":
      G.add_edge(module.name, "libtbx")

    reqs = {x for x in modules if x.name in module.required}
    if len(reqs) < len(module.required):
      print("{} has missing dependency: {}".format(module.name, module.required - {x.name for x in reqs}))
    # # Add 
    # for dep in reqs:
    #   dep.required_by.add(module)
    # module.required = reqs


  # Custom edges to fix problems - not sure how order is determined without this
  G.add_edge("scitbx", "omptbx")

  try:
    cycle = nx.cycles.find_cycle(G)
  except nx.NetworkXNoCycle:
    pass
  else:
    raise RuntimeError("Cycles found in dependency graph: {}".format(cycle))

  # Find an order of processing that satisfies dependencies
  node_order = nx.topological_sort(G, reverse=True, nbunch=sorted(G.nodes()))
  print "Import order: ", node_order
  # import pdb
  # pdb.set_trace()

  # Say what we found
  print("Found modules (excluding modules without SConscripts):")
  maxl = max(len(x.name) for x in modules)
  for module in sorted(modules, key=lambda x: x.name):
    if module.has_sconscript:
      print("  {}  {}".format(module.name.ljust(maxl), module.path))

  # Contain the continuing scons environment we are building
  scons = SconsBuilder(dist=MODULE_PATH, modules=modulemap)

  # Process modules (with SConscripts) in dependency order
  for module in [modulemap[x] for x in node_order if x in modulemap and modulemap[x].has_sconscript]:
    scons.parse_module(module)
