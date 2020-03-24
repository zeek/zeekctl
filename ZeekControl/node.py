#
# One ZeekControl node.
#

import os
import copy

from ZeekControl import doc

class Node:
    """Class representing one node of the ZeekControl maintained setup. In
    standalone mode, there's always exactly one node of type ``standalone``. In
    a cluster setup, there is zero or more of type ``logger``, exactly one of
    type ``manager``, one or more of type ``proxy``, and zero or more of type
    ``worker``.  The manager will handle writing logs if there are no loggers
    defined in a cluster.

    A ``Node`` object has a number of keys with values that are set via the
    ``node.cfg`` file and can be accessed directly (from a plugin) via
    corresponding Python attributes (e.g., ``node.name``):

        ``name`` (string)
            The name of the node, which corresponds to the ``[<name>]``
            section in ``node.cfg``.

        ``type`` (string)
            The type of the node.  In a standalone configuration, the only
            allowed type is ``standalone``.  In a cluster configuration, the
            type must be one of: ``logger``, ``manager``, ``proxy``,
            or ``worker``.

        ``host`` (string)
            The hostname or IP address of the system the node is
            running on.  Every node must specify a host.

        ``interface`` (string)
            The network interface for the Zeek worker (or standalone node) to
            use; empty if not set.

        ``lb_procs`` (integer)
            The number of clustered Zeek workers you'd like to start up.  If
            specified, this number must be greater than zero and a load
            balancing method must also be specified.  This option is valid only
            for worker nodes.

        ``lb_method`` (string)
            The load balancing method to distribute packets to all of the
            Zeek workers.  This must be one of: ``pf_ring``, ``myricom``,
            ``custom``, or ``interfaces``.  This option can have a value
            only if the ``lb_procs`` option has a value.

        ``lb_interfaces`` (string)
            A comma-separated list of network interface names for the Zeek
            worker to use.  The number of interfaces in this list must
            equal the value of the ``lb_procs`` option.

            This option can be specified only when the load balancing method
            is ``interfaces``.

        ``pin_cpus`` (string)
            A comma-separated list of CPU numbers to which the node's Zeek
            processes will be pinned.  If not specified, then CPU pinning will
            not be used for this node.  This option is supported only on
            Linux and FreeBSD, and is ignored on all other platforms.

            CPU numbering starts at zero (e.g.,
            the only valid CPU numbers for a machine with one dual-core
            processor would be 0 and 1).  If the length of this list does not
            match the number of Zeek processes for this node, then some CPUs
            could have zero (if too many CPU numbers are specified) or more
            than one (if not enough CPU numbers are specified) Zeek processes
            pinned to them.  Only the specified CPU numbers will be used,
            regardless of whether additional CPU cores exist.

        ``env_vars`` (string)
            A comma-separated list of environment variables to set when
            running Zeek (e.g., ``env_vars=VAR1=1,VAR2=2``).  These
            node-specific values override any global values specified in
            the ``zeekctl.cfg`` file.

        ``aux_scripts`` (string)
            Any node-specific Zeek script configured for this node.

        ``zone_id`` (string)
            If ZeekControl is managing a cluster comprised of nodes
            using non-global IPv6 addresses, then this configures the
            :rfc:`4007` ``zone_id`` string that the node associates with
            the common zone that all cluster nodes are a part of.  This
            identifier may differ between nodes.

    Any attribute that is not defined in ``node.cfg`` will be empty.

    In addition, plugins can override `Plugin.nodeKeys`_ to define their own
    node keys, which can then be likewise set in ``node.cfg``. The key names
    will be prepended with the plugin's `Plugin.prefix`_ (e.g., for the plugin
    ``test``, the node key ``foo`` is set by adding ``test.foo=value`` to
    ``node.cfg``).

    Finally, a Node object has the following methods that can be called
    from a plugin:
    """

    # Valid keys in nodes file. The values will be stored in attributes of the
    # same name. Custom keys can be add via addKey().
    _keys = {"type": 1, "host": 1, "interface": 1, "aux_scripts": 1,
             "zeekbase": 1, "ether": 1, "zone_id": 1,
             "lb_procs": 1, "lb_method": 1, "lb_interfaces": 1,
             "pin_cpus": 1, "env_vars": 1, "count": 1}


    def __init__(self, config, name):
        """Instantiates a new node of the given name."""
        self.name = name
        self._config = config

        for key in Node._keys:
            self.__dict__[key] = ""

    def __str__(self):
        return self.name

    def copy(self):
        n = Node(self._config, self.name)

        for key in self.__dict__:
            if key.startswith("_"):
                # This is to avoid copying _config, which causes problems.
                setattr(n, key, getattr(self, key))
            else:
                # Must make a copy of some config items (e.g. env_vars) so that
                # changes to the value only affect one node.
                setattr(n, key, copy.copy(getattr(self, key)))

        return n

    def items(self):
        """Returns a list of (key, value) tuples, sorted by key, of a node."""

        def tostr(v):
            if isinstance(v, dict):
                return ",".join(["%s=%s" % (key, val) for (key, val) in sorted(v.items())])
            else:
                return str(v)

        return [(k, tostr(self.__dict__[k])) for k in sorted(self.__dict__.keys())]

    @doc.api
    def describe(self):
        """Returns an extended string representation of the node including all
        its keys with values (sorted by key)."""

        def fmt(v):
            if isinstance(v, list):
                v = ",".join(v)
            elif isinstance(v, dict):
                v = ",".join(["%s=%s" % (key, val) for (key, val) in sorted(v.items())])

            return v

        # Do not output attributes starting with underscore, because they are
        # for internal use and don't provide useful information to the user.
        return ("%16s - " % self.name) + " ".join(["%s=%s" % (k, fmt(self.__dict__[k])) for k in sorted(self.__dict__.keys()) if not k.startswith("_")])

    def to_dict(self):
        d = dict(self.items())
        d["name"] = self.name
        d["description"] = self.describe()
        return d

    @doc.api
    def cwd(self):
        """Returns a string with the node's working directory."""
        return os.path.join(self._config.spooldir, self.name)

    def setPID(self, pid):
        """Stores the process ID of the node's Zeek process."""
        key = "%s-pid" % self.name
        self._config.set_state(key, pid)
        key = "%s-host" % self.name
        self._config.set_state(key, self.host)

    @doc.api
    def getPID(self):
        """Returns the process ID of the node's Zeek process if running, and
        None otherwise."""
        key = "%s-pid" % self.name
        return self._config.get_state(key)

    def clearPID(self):
        """Clears the stored process ID for the node's Zeek process, indicating
        that it is no longer running."""
        key = "%s-pid" % self.name
        self._config.set_state(key, None)

    def setCrashed(self):
        """Marks node's Zeek process as having terminated unexpectedly."""
        key = "%s-crashed" % self.name
        self._config.set_state(key, True)

    def clearCrashed(self):
        """Clears the mark for the node's Zeek process having terminated
        unexpectedly."""
        key = "%s-crashed" % self.name
        self._config.set_state(key, False)

    @doc.api
    def hasCrashed(self):
        """Returns True if the node's Zeek process has exited abnormally."""
        key = "%s-crashed" % self.name
        val = self._config.get_state(key)
        if val is None:
            val = False
        return val

    def getExpectRunning(self):
        """Returns True if we expect the node's Zeek process to be running."""
        key = "%s-expect-running" % self.name
        val = self._config.get_state(key)
        if val is None:
            val = False
        return val

    def setExpectRunning(self, val):
        key = "%s-expect-running" % self.name
        self._config.set_state(key, val)

    def setPort(self, port):
        """Set the Zeek port this node is using."""
        key = "%s-port" % self.name
        self._config.set_state(key, port)

    @doc.api
    def getPort(self):
        """Returns an integer with the port number that this node's
        communication system is listening on for incoming connections, or -1 if
        no such port has been set yet.
        """
        key = "%s-port" % self.name
        return self._config.get_state(key) or -1

    @staticmethod
    def addKey(kw):
        """Adds a supported node key. This is used by the PluginRegistry to
        register custom keys."""

        # We need to convert to lowercase here because Python's configparser
        # automatically converts keys to lowercase when reading node.cfg.
        Node._keys[kw.lower()] = 1


# The sorting order for node types used by the sorting functions below
# (specifying the sort order explicitly is useful if we don't want to
# use alphabetical order).
_typeorder = ("standalone", "logger", "manager", "proxy", "worker")

# Sorting key function for a list of nodes.
def sortnode(n):
    try:
        return _typeorder.index(n.type), n.count
    except ValueError:
        return len(_typeorder), n.count

# Sorting key function for a list of tuples, where the first tuple element is
# a node.
def sorttuple(t):
    n = t[0]
    try:
        return _typeorder.index(n.type), n.count
    except ValueError:
        return len(_typeorder), n.count

# Given a list of nodes (all of the same type), return a string that describes
# the list of nodes (in either singular or plural form).  This string is
# just for informational output, and doesn't have any other use or meaning.
# For standalone node type, the node name is returned instead.
def nodes_describe(nodes):
    nodetype = nodes[0].type

    if nodetype == "standalone":
        return nodes[0].name
    elif nodetype == "manager":
        return "manager"
    elif nodetype == "logger":
        return "logger%s" % ("" if len(nodes) == 1 else "s")
    elif nodetype == "proxy":
        return "prox%s" % ("y" if len(nodes) == 1 else "ies")
    elif nodetype == "worker":
        return "worker%s" % ("" if len(nodes) == 1 else "s")

# Return a list of all node types.
def node_types():
    return ["logger", "manager", "proxy", "worker", "standalone"]

# Check if the given node is a certain type.
def is_standalone(n):
    return n.type == "standalone"

def is_manager(n):
    return n.type == "manager"

def is_logger(n):
    return n.type == "logger"

def is_proxy(n):
    return n.type == "proxy"

def is_worker(n):
    return n.type == "worker"

# Given a list of nodes, return separate lists for each type of node.
def separate_types(nodes):
    loggers = []
    manager = []
    proxies = []
    workers = []

    for n in nodes:
        if n.type == "worker":
            workers += [n]
        elif n.type == "proxy":
            proxies += [n]
        elif n.type in ("manager", "standalone"):
            manager += [n]
        elif n.type == "logger":
            loggers += [n]

    return loggers, manager, proxies, workers

# Map of node groups to node types (here, "_ALL_" is for internal use only and
# matches all node types).
grouptype = {"all": "_ALL_",
             "loggers": "logger",
             "manager": "manager",
             "proxies": "proxy",
             "workers": "worker"}

# Return a list of all node groups.  These are for convenience when using
# zeekctl commands (e.g. "zeekctl start workers").
def node_groups():
    return list(grouptype.keys())

# Return the node type (or "_ALL_", which matches all node types) of a
# specified group name.  If the "tag" doesn't match any group name, then None
# is returned.
def group_type(tag):
    return grouptype.get(tag)

# Return the name of a node group.
def manager_group():
    return "manager"

def logger_group():
    return "loggers"

def proxy_group():
    return "proxies"

def worker_group():
    return "workers"
