# coding: utf-8

"""
Reads a tree of SConscripts and extracts module and target information
"""

import os
import sys
import networkx as nx
import collections
import itertools

from .utils import return_as_list
from .sconsemu import SconsEmulator

import logging
logger = logging.getLogger(__name__)

class LibTBXModule(object):
  """Represents a libtbx module"""
  def __init__(self, name, path, module_root):
    self.name = name
    self.path = path
    self.module_root = module_root
    self.required = set()
    self.targets = []
    # self.required_by = set()

    if self.has_config:
      # Read the configuration for a basic dependency tree
      with open(os.path.join(self.module_root, self.path, "libtbx_config")) as f:
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
    return os.path.isfile(os.path.join(self.module_root, self.path, "SConscript"))
  @property
  def has_config(self):
    return os.path.isfile(os.path.join(self.module_root, self.path, "libtbx_config"))

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
    yield LibTBXModule(name=name, path=path, module_root=modulepath)


class TargetCollection(collections.Set):
  """Collection wrapper to make operations on target sets easier"""
  def __init__(self, distribution):
    self.distribution = distribution

  def __contains__(self, target):
    # The target must have a module to be in the distribution
    if target.module is None:
      return False
    # The target module must exist identically in this distribution
    if not target.module is self.distribution._modules.get(target.module.name):
      return False
    assert target in target.module.targets, "Target-modules out of sync"
    return True

  def __iter__(self):
    return itertools.chain(*(x.targets for x in self.distribution._modules.values()))
  
  def __len__(self):
    return sum(len(x.targets) for x in self.distribution._modules.values())

  @classmethod
  def _from_iterable(cls, it):
      return set(it)

  def remove(self, target):
    assert target in self
    target.module.targets.remove(target)
    target.module = None

  def remove_all(self, targets):
    for target in targets:
      self.remove(target)

class TBXDistribution(object):
  """Holds collected information about a TBX distribution and it's targets"""
  def __init__(self):
    self.module_path = None
    self._modules = {}
    self._targetcollection = TargetCollection(self)

  @property
  def targets(self):
    """Returns a iterator over all targets in the distribution"""
    return self._targetcollection

  @property
  def modules(self):
    return self._modules

def _build_dependency_graph(modules):
  """Builds a networkX dependency graph out of the module self-reported requirements.

  :param modules: A list of modules.
  """

  G = nx.DiGraph()
  G.add_nodes_from(x.name for x in modules)

  # Build the dependency graph from the libtbx information
  for module in modules:
    for req in module.required:
      G.add_edge(module.name, req)
    
    # Force a dependency on libtbx so it goes before everything else
    if not module.name == "libtbx":
      G.add_edge(module.name, "libtbx")

    # Check that we know about all the dependencies, and warn if we don't
    reqs = {x for x in modules if x.name in module.required}
    if len(reqs) < len(module.required):
      print("{} has missing dependency: {}".format(module.name, module.required - {x.name for x in reqs}))

  # Custom edges to fix problems - not sure how order is determined without this
  G.add_edge("scitbx", "omptbx")

  # Validate we don't have any cycles
  assert nx.is_directed_acyclic_graph(G), "Cycles found in dependency graph: {}".format(nx.cycles.find_cycle(G))

  return G

##############################################################################
# __main__ handling and setup functionality

def _deduplicate_target_names(targets):
  "Takes a list of targets and fixes names to avoid duplicates"
  namecount = Counter([x.name for x in targets])
  for duplicate in [x for x in namecount.keys() if namecount[x] > 1]:
    duped = [x for x in targets if x.name == duplicate]
    modules = set(x.tbxmodule for x in duped)
    assert len(modules) == len(duped), "Module name not enough to disambiguate duplicate targets named {} (in {})".format(duplicate, modules)
    for target in duped:
      target.name = "{}_{}".format(target.name, target.tbxmodule)
  assert all([x == 1 for _, x in Counter([x.name for x in targets]).items()]), "Deduplication failed"

def read_module_path_sconscripts(module_path):
  """Parse all modules/SConscripts in a tbx module root.

  Returns a TBXDistribution object.
  """

  modules = {x.name: x for x in find_libtbx_modules(module_path)}
  # Make a lookup to find modules by name
  # modulemap = {x.name: x for x in modules}

  # Find an order of processing that satisfies dependencies
  G = _build_dependency_graph(modules.values())
  node_order = nx.topological_sort(G, reverse=True, nbunch=sorted(G.nodes()))
  logger.debug("Dependency processing order: {}".format(node_order))

  # Prepare the SCons emulator
  scons = SconsEmulator(dist=module_path)#, modules=modules)

  # Process all modules in the determined dependency order
  scons_modules = [modules[x] for x in node_order if x in modules and modules[x].has_sconscript]
  for module in scons_modules:
    scons.parse_module(module)

  # Say what we found
  logger.info("Found modules (excluding modules without SConscripts):")
  maxl = max(len(x.name) for x in modules.values())
  for module in sorted(modules.values(), key=lambda x: x.name):
    if module.has_sconscript:
      logger.info("  {}  {}".format(module.name.ljust(maxl), module.path))


  logger.info("Processing of SConscripts done.")
  logger.info("{} Targets recognised".format(len(scons.targets)))

  tbx = TBXDistribution()
  tbx.module_path = module_path
  tbx._modules = modules

  return tbx

def _filter_targets(targets):
  """Apply filters to targets in a list of modules."""

  # Extract the target information from this
  # targets = itertools.chain(*[x.targets for x in modules])
  
  # Remove any boost libraries that might be explicitly compiled
  remove_boost = {"boost_thread", "boost_system", "boost_python", "boost_chrono"}
  for boost in remove_boost:
    tgt = [x for x in targets if x.name == boost]
    for t in tgt:
      yield t
      # logger.info("Removing target {}".format(t.name))
      # targets.remove(t)
      # # Remove this target from the module that points to it
      # t.module.targets.remove(t)

  # Remove clipper and clipper_adaptbx because not sure how SCons resolves paths
  # e.g. clipper adaptbx says "../clipper/<x>" but that's in cctbx_project and so
  # an invalid path reference, but SCons finds it.
  remove_mods = {"clipper", "clipper_adaptbx"}
  for mod in remove_mods:
    tgts = [x for x in targets if x.tbxmodule.name == mod]
    for t in tgts:
      logger.info("Removing target {} (removing {})".format(t.name, mod))
      targets.remove(t)
      t.module.targets.remove(t)

# def read_tbx_distribution(module_path):
#   tbx = TBXDistribution.from_module_path(module_path)




def main(args=None):
  logging.basicConfig(level=logging.INFO)

  if args is None:
    args = sys.argv[1:]
  if "-h" in args or "--help" in args or len(args) != 1 or not os.path.isdir(args[0]):
    print("Usage: read_scons.py <module_path>")
    return 0

  module_path = args[0]

  # tbx = build_distribution_from_module_path(module_path)
  # import pdb
  # pdb.set_trace()
  tbx = read_module_path_sconscripts(module_path)

  # Remove the boost targets
  boost_target_names = {"boost_thread", "boost_system", "boost_python", "boost_chrono"}
  boost_targets = {x for x in tbx.targets if x.name in boost_target_names}
  for target in boost_targets:
    logger.info("Removing target {} (in {})".format(target.name, target.module.name))
    tbx.targets.remove(target)

  # Remove any modules we don't want
  for module in {"clipper", "clipper_adaptbx"}:
    if module in tbx.modules:
      logger.info("Removing module {} ({} targets)".format(module, len(tbx.modules[module].targets)))
      del tbx.modules[module]

  all_libs = set(itertools.chain(*[x.extra_libs for x in tbx.targets]))
  logger.info("All linked libraries: {}".format(", ".join(all_libs)))
  logger.info("All external (w/o known like boost): {}".format(", ".join(all_libs - {x.name for x in tbx.targets})))
  logger.info("{} Targets remaining".format(len(tbx.targets)))

  import pdb
  pdb.set_trace()


  # Fix any duplicated target names
  _deduplicate_target_names(targets)

  # Find the python-module targets and change their target type
  for target in targets:
    if target.boost_python and not target.prefix:
      target.type = Target.Type.MODULE

  # Validate known cases of shared sources
  KNOWN_IGNORABLE_SHARED = [
    ['numpy_bridge.cpp'],
    ['lbfgs_fem.cpp'],
    ['boost_python/outlier_helpers.cc'],
    ['nanoBragg_ext.cpp', 'nanoBragg.cpp']
  ]
  for target in [x for x in targets if x.shared_sources]:
    src = target.shared_sources[0].path
    if isinstance(src, basestring):
      src = [src]
    if src in KNOWN_IGNORABLE_SHARED:
      target.sources.extend(src)
      target.shared_sources = []

  # Check assumptions about libraries
  assert all(x.tbxmodule for x in targets)
  assert all(x.prefix == "lib" for x in targets if x.type == Target.Type.SHARED)
  assert all(x.prefix == "lib" for x in targets if x.type == Target.Type.STATIC)
  assert all(x.prefix == "" for x in targets if x.type == Target.Type.MODULE)
  assert all(not x.shared_sources for x in targets), "Shared sources exists - all should be filtered"

  # Can't: Not all python libraries end up in lib
  # assert all(x.output_path == "#/lib" for x in targets if x.type == Target.Type.MODULE)
  

  # Build an export dictionary
  # module_data = defaultdict(list)
  # target_data = []
  scons_data = {
    "targets": [],
    "modules": []
  }

  for module in (x for x in modules if x.targets):
    scons_data["modules"].append({
      "path": module.path,
      "name": module.name
    })

  for target in targets:
    tdict = {
      "name": target.name,
      "type": target.type.value.lower(),
      "origin": target.origin_path,
      "sources": list(target.sources),
      "module": target.tbxmodule.name,
    }
    if target.filename != target.name:
      tdict["filename"] = target.filename
    if target.output_path != "#/lib":
      tdict["output_path"] = target.output_path
    if target.extra_libs:
      tdict["dependencies"] = list(target.extra_libs)

    scons_data["targets"].append(tdict)



  # # module_data = dict(module_data)
  # import code
  # code.interact(local=locals())

  with open("scons_targets.yml", "w") as f:
    f.write(yaml.dump(scons_data))


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))