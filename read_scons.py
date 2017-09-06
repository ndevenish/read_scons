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

import networkx as nx

def return_as_list(f):
  """Decorated a function to convert a generator to a list"""
  def _wrap(*args, **kwargs):
    return list(f(*args, **kwargs))
  return _wrap

class Module(object):
  """Represents a module"""
  def __init__(self, name, path):
    self.name = name
    self.path = path
    self.required = set()
    self.required_by = set()

    if self.has_config:
      print "Parsing ", self.path
      with open(os.path.join(self.path, "libtbx_config")) as f:
        self._config = eval(f.read())
        self.required = set(self._config.get("modules_required_for_build", set()))
        # Handle aliases/multis
        if "boost" in self.required:
          self.required.add("boost_adaptbx")
          self.required.remove("boost")
        if "annlib" in self.required:
          self.required.add("annlib_adaptbx")
          self.required.remove("annlib")

# {
#   "modules_required_for_build": ["boost"],
#   "modules_required_for_use": ["boost_adaptbx", "omptbx"],
#   "optional_modules": ["fable"]
# }
  def __repr__(self):
    return "Module(name={}, path={})".format(repr(self.name), repr(self.path))
  @property
  def has_sconscript(self):
    return os.path.isfile(os.path.join(self.path, "SConscript"))
  @property
  def has_config(self):
    return os.path.isfile(os.path.join(self.path, "libtbx_config"))


@return_as_list
def find_modules(modulepath):
  """Find all modules in a path"""

  # Find all direct subdirs, plus all in cctbx_project
  subdirs = list(next(os.walk(modulepath))[1])
  if "cctbx_project" in subdirs:
    for dirname in next(os.walk(os.path.join(modulepath, "cctbx_project")))[1]:
      subdirs.append(os.path.join("cctbx_project", dirname))

  # Search each directory for a libtbx_config file. If it has one, it's a module
  for dirname in subdirs:
    if  os.path.isfile(os.path.join(dirname, "libtbx_config")) or \
        os.path.isfile(os.path.join(dirname, "SConscript")):
      name = os.path.basename(dirname)
      path = dirname
      yield Module(name=name, path=path)

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
    assert False, "Not recognised TryCompile"

  def Finish(self):
    pass

# 

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
      }
      defaults.update(kwargs)
      self.kwargs = defaults

    def Append(self, **kwargs):
      for key, val in kwargs.items():
        if not key in self.kwargs:
          self.kwargs[key] = []
        self.kwargs[key].append(val)
      # self.kwargs.update(kwargs)

    def Replace(self, **kwargs):
      self.kwargs.update(kwargs)

    def Configure(self):
      return SConsConfigurationContext()

    def Clone(self):
      clone = type(self)()
      clone.parent = self
      return clone

    def __setitem__(self, key, value):
      self.kwargs[key] = value

    def __getitem__(self, key):
      return self.kwargs[key]

  return _SconsEnvironment

class FakePath(object):
  pass

class UnderBuild(FakePath):
  def __init__(self, path):
    self.path = path
  def __repr__(self):
    return "UnderBuild({})".format(repr(self.path))
  def __abs__(self):
    return self

class UnderBase(FakePath):
  def __init__(self, path):
    self.path = path
  def __repr__(self):
    return "UnderBuild({})".format(repr(self.path))

class PythonIncludePath(FakePath):
  def split(self, *args):
    return ["PYTHONINCLUDEPATH"]
  # def __getitem__(self, key):
  #   import pdb
  #   pdb.set_trace()
  #   return self
  # def __add__(self, other):
  #   return self

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

class libtbxEnv(object):
  def __init__(self):
    self.build_options = libtbxBuildOptions()

  def under_build(self, path):
    return UnderBuild(path)

  def under_base(self, path):
    return UnderBase(path)

  def dist_path(self, path):
    return os.path.join("DISTPATH", path)

  @property
  def build_path(self):
    return UnderBuild(".")

  @property
  def lib_path(self):
    return UnderBuild("lib")

class libtbxIncludeRegistry(list):
  def scan_boost(self, *args, **kwargs):
    pass

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

def _wrappedOpen(file, mode=None):
  return _fakeFile(file)
  # assert False, "Unknown Open; {}/{}".format(file, mode)

class SconsBuilder(object):
  def __init__(self):
    self._exports = {}

  def parse_module(self, module):
    scons = os.path.join(module.path, "SConscript")
    if not os.path.isfile(scons):
      print("No Sconscript for module {}".format(module.name))
      return
    print "Parsing {}".format(module.name)
    # Build the object used to run the script
    module = InjectableModule(scons)

    # Build the Scons injection environment
    _to_export = set()
    def _env_export(self, *args):
      print "Exporting ", args
      _to_export.update(set(args))

    inj = {
      "Environment": _generate_sconsbaseenv(self),
      "open": _wrappedOpen,
      "ARGUMENTS": {},
      "Builder": _SConsBuilder,
      "Export": _env_export
    }
    # Inject this and execute
    module.inject(inj)
    module.execute()
    for name in _to_export:
      self._exports[name] = module.getvar(name)


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
libtbx.easy_run = libtbxEasyRun()
libtbx.utils.getenv_bool = _fail
libtbx.str_utils.show_string = _fail
libtbx.path.norm_join = _fail
libtbx.path.full_command_path = _fail
libtbx.group_args = AttrDict
libtbx.env_config.include_registry = libtbxIncludeRegistry
libtbx.env_config.is_64bit_architecture = lambda: True
libtbx.env_config.python_include_path = PythonIncludePath
# Too complex to try shortcutting; just fall through where used
def _libtbx_select_matching(key, choices, default=None):
  for key_pattern, value in choices:
    m = re.search(key_pattern, key)
    if m is not None: return value
  return default
libtbx.utils.select_matching = _libtbx_select_matching


libtbx.env = libtbxEnv()

# Fake anything SCons that we interact with
SCons = new_module("SCons")
SCons.Action = new_module("SCons.Action")
SCons.Scanner = new_module("SCons.Scanner")
SCons.Scanner.C = new_module("SCons.Scanner.C")

SCons.Action.FunctionAction = Mock()
SCons.Scanner.C.CScanner = Mock()

if __name__ == "__main__":
  modules = find_modules(".")
  modulemap = {}

  G = nx.DiGraph()

  # Build the dependency graph from the libtbx information
  for module in modules:
    modulemap[module.name] = module

    G.add_node(module.name)
    for req in module.required:
      G.add_edge(module.name, req)
    # Force a dependency on libtbx so it goes first
    if not module.name == "libtbx":
      G.add_edge(module.name, "libtbx")

    reqs = {x for x in modules if x.name in module.required}
    if len(reqs) < len(module.required):
      print("{} has missing dependency: {}".format(module.name, module.required - {x.name for x in reqs}))
    for dep in reqs:
      dep.required_by.add(module)
    module.required = reqs

  try:
    nx.cycles.find_cycle(G)
  except nx.NetworkXNoCycle:
    pass
  else:
    raise RuntimeError("Cycles found in dependency graph")

  # Find an order of processing
  node_order = nx.topological_sort(G, reverse=True)

  # import pdb
  # pdb.set_trace()

  # Say what we found
  print("Found modules:")
  maxl = max(len(x.name) for x in modules)
  for module in sorted(modules, key=lambda x: x.name):
    print("  {}  {}".format(module.name.ljust(maxl), module.path))

  # Contain the continuing scons environment we are building
  scons = SconsBuilder()

  # # Find the libtbx module and do that first
  # libtbx = [x for x in modules if x.name == "libtbx"][0]
  # scons.parse_module(libtbx)

  # # Now do every other module
  for module in [modulemap[x] for x in node_order if x in modulemap and modulemap[x].has_sconscript]:
    scons.parse_module(module)
