# coding: utf-8

"""
Prepares the import environment for running the tbx SCons scripts
"""

import os
import sys
import re
from types import ModuleType
from mock import Mock
import contextlib

from .utils import AttrDict
from .tbxemu import *
from .utils import monkeypatched

def new_module(name, doc=None):
  """Create a new module and inject it into sys.modules.

  :param name: Fully qualified name (including parent .)
  :returns:  A module, injected into sys.modules
  """
  m = ModuleType(name, doc)
  m.__file__ = name + '.py'
  sys.modules[name] = m
  return m

# Common functions
def _fail(*args, **kwargs):
  raise NotImplementedError("Not Implemented")
def _wtf(*args, **kwargs):
  assert False, "WTF? {}, {}".format(args, kwargs)


def _unique_paths(paths):
  return list(set(paths))

def _libtbx_select_matching(key, choices, default=None):
  # Too complex to try shortcutting the test; just replicate and catch results
  for key_pattern, value in choices:
    m = re.search(key_pattern, key)
    if m is not None: return value
  return default


def _tbx_darwin_shlinkcom(env_etc, env, lo, dylib):
  # Don't understand the purpose or intent of this functions, but seems 
  # mostly ignorable without damage.
  if "libboost_thread.lo" in lo:
    return
  if "libboost_python.lo" in lo:
    return
  if "libboost_system.lo" in lo:
    return
  _wtf(env_etc, env, lo, dylib)

class EasyRunResult(object):
  """Simple wrapper to pretend to be the output from an easy_run"""
  def __init__(self, output):
    self.stdout_lines = list(output)
  def raise_if_errors(self):
    return self

def _tbx_easyrun_fully_buffered(command, **kwargs):
  """Check what the caller was trying to run, and return pretend data"""
  if command == "/usr/bin/uname -p":
    return EasyRunResult(["i386"])
  elif command == "/usr/bin/sw_vers -productVersion":
    return EasyRunResult(["10.12.0"])
  elif command == "nvcc --version":
    return EasyRunResult(["Cuda compilation tools, release 8.0, V8.0.61"])
  assert False, "No command known; {}".format(command)

# Only allow this to be done once, until we may add e.g. context-patching
_patching_done = False

def do_import_patching():
  # Only do this once
  global _patching_done
  if _patching_done:
    return

  # Create the libtbx environment
  libtbx = new_module("libtbx")
  libtbx.load_env = new_module("libtbx.load_env")
  libtbx.env_config = new_module("libtbx.env_config")
  libtbx.utils = new_module("libtbx.utils")
  libtbx.str_utils = new_module("libtbx.str_utils")
  libtbx.path = new_module("libtbx.path")

  libtbx.manual_date_stamp = 20090819 # I don't even
  libtbx.utils.getenv_bool = _fail
  libtbx.str_utils.show_string = _fail
  libtbx.path.norm_join = lambda a,b: os.path.normpath(os.path.join(a,b))
  libtbx.path.full_command_path = _fail
  libtbx.group_args = AttrDict

  libtbx.env_config.include_registry = libtbxIncludeRegistry
  libtbx.env_config.is_64bit_architecture = lambda: True
  libtbx.env_config.python_include_path = lambda: "PYTHON/INCLUDE/PATH"
  libtbx.env_config.unique_paths = _unique_paths
  libtbx.env_config.darwin_shlinkcom = _tbx_darwin_shlinkcom

  libtbx.utils.select_matching = _libtbx_select_matching
  libtbx.utils.warn_if_unexpected_md5_hexdigest = Mock()
  libtbx.utils.write_this_is_auto_generated =  Mock()

  libtbx.env = libtbxEnv()
  libtbx.easy_run = new_module("libtbx.easy_run")
  libtbx.easy_run.fully_buffered = _tbx_easyrun_fully_buffered

  # data module used during it's sconscript
  fftw3tbx = new_module("fftw3tbx")
  fftw3tbx.fftw3_h = "fftw3.h"

  # Occasionally we access some SCons API to do... something
  SCons = new_module("SCons")
  SCons.Action = new_module("SCons.Action")
  SCons.Scanner = new_module("SCons.Scanner")
  SCons.Scanner.C = new_module("SCons.Scanner.C")

  SCons.Action.FunctionAction = Mock()
  SCons.Scanner.C.CScanner = Mock()

# def monkeypatched(object, name, patch):
#   """ Temporarily monkeypatches an object. """
#   pre_patched_value = getattr(object, name)
#   setattr(object, name, patch)
#   yield object
#   setattr(object, name, pre_patched_value)
