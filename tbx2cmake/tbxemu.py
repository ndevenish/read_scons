# coding: utf-8

import os

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
  mode = "invalid" # AFAICT this is only tested as mode == "profile" (linux only)
  static_libraries = False

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
