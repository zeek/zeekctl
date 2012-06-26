#
# One BroControl node.
#

import doc
import config
import os

class Node:
    """Class representing one node of the BroControl maintained setup. In
    standalone mode, there's always exactly one node of type ``standalone``. In
    a cluster setup, there is exactly one of type ``manager``, and zero or
    more of type ``proxy`` and ``worker``.

    In addition to the methods described above, a ``Node`` object has a number
    of keys with values that are set via ``node.cfg`` and can be accessed
    directly via corresponding Python attributes (e.g., ``node.name``):

        ``name`` (string)
            The name of the node, which corresponds to the ``[<name>]``
            section in ``node.cfg``.

        ``type`` (string)
            The type of the node, which will be one of ``standalone``,
            ``manager``, ``proxy``, and ``worker``.

        ``host`` (string)
            The hostname of the system the node is running on.

        ``interface`` (string)
            The network interface for Bro to use; empty if not set.

        ``lb_procs`` (integer)
            The number of clustered Bro workers you'd like to start up.

        ``lb_method`` (string)
            The load balancing method to distribute packets to all of the 
            processes (must be one of: ``pf_ring``, ``myricom``, or
            ``interfaces``).

        ``lb_interfaces`` (string)
            If the load balancing method is ``interfaces``, then this is
            a comma-separated list of network interface names to use.

        ``aux_scripts`` (string)
            Any node-specific Bro script configured for this node.

        ``zone_id`` (string)
            If BroControl is managing a cluster comprised of nodes
            using non-global IPv6 addresses, then this configures the
            RFC 4007 ``zone_id`` string that the node associates with
            the common zone that all cluster nodes are a part of.  This
            identifier may differ between nodes.

    Any attribute that is not defined in ``node.cfg`` will be empty.

    In addition, plugins can override `Plugin.nodeKeys`_ to define their own
    node keys, which can then be likewise set in ``node.cfg``. The key names
    will be prepended with the plugin's `Plugin.prefix`_ (e.g., for the plugin
    ``test``, the node key ``foo`` is set by adding ``test.foo=value`` to
    ``node.cfg``).
    """

    # Valid keys in nodes file. The values will be stored in attributes of the
    # same name. Custom keys can be add via addKey().
    _keys = { "type": 1, "host": 1, "interface": 1, "aux_scripts": 1, 
              "brobase": 1, "ether": 1, "zone_id": 1,
              "lb_procs": 1, "lb_method": 1, "lb_interfaces": 1 }


    def __init__(self, name):
        """Instantiates a new node of the given name."""
        self.name = name
        self.env_vars = []

        for key in Node._keys:
            self.__dict__[key] = ""

    def __str__(self):
        return self.name

    @doc.api
    def describe(self):
        """Returns an extended string representation of the node including all
        its keys with values."""
        def fmt(v):
            if type(v) == type([]):
                v = ",".join(v)
            return v

        return ("%15s - " % self.name) + " ".join(["%s=%s" % (k, fmt(self.__dict__[k])) for k in sorted(self.__dict__.keys())])

    @doc.api
    def cwd(self):
        """Returns a string with the node's working directory."""
        return os.path.join(config.Config.spooldir, self.name)

    # Stores the nodes process ID.
    def setPID(self, pid):
        """Stores the process ID for the node's Bro process."""
        config.Config._setState("%s-pid" % self.name, str(pid))

    @doc.api
    def getPID(self):
        """Returns the process ID of the node's Bro process if running, and
        None otherwise."""
        t = "%s-pid" % self.name.lower()
        if t in config.Config.state:
            try:
                return int(config.Config.state[t])
            except ValueError:
                pass

        return None

    def clearPID(self):
        """Clears the stored process ID for the node's Bro process, indicating
        that it is no longer running."""
        config.Config._setState("%s-pid" % self.name, "")

    def setCrashed(self):
        """Marks node's Bro process as having terminated unexpectedly."""
        config.Config._setState("%s-crashed" % self.name, "1")

    # Unsets the flag for unexpected termination.
    def clearCrashed(self):
        """Clears the mark for the node's Bro process having terminated
        unexpectedly."""
        config.Config._setState("%s-crashed" % self.name, "0")

    # Returns true if node has terminated unexpectedly.
    @doc.api
    def hasCrashed(self):
        """Returns True if the node's Bro process has exited abnormally."""
        t = "%s-crashed" % self.name.lower()
        return t in config.Config.state and config.Config.state[t] == "1"

    # Set the Bro port this node is using.
    def setPort(self, port):
        config.Config._setState("%s-port" % self.name, str(port))

    # Get the Bro port this node is using.
    @doc.api
    def getPort(self):
        """Returns an integer with the port that this node's communication
        system is listening on for incoming connections, or -1 if no such port
        has been set yet.
        """
        t = "%s-port" % self.name.lower()
        return t in config.Config.state and int(config.Config.state[t]) or -1

    @staticmethod
    def addKey(kw):
        """Adds a supported node key. This is used by the PluginRegistry to
        register custom keys."""

        Node._keys[kw] = 1
