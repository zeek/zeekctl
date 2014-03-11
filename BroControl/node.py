#
# One BroControl node.
#

import os

import doc
import config

class Node:
    """Class representing one node of the BroControl maintained setup. In
    standalone mode, there's always exactly one node of type ``standalone``. In
    a cluster setup, there is exactly one of type ``manager``, one or
    more of type ``proxy``, and zero or more of type ``worker``.

    In addition to the methods described above, a ``Node`` object has a number
    of keys with values that are set via ``node.cfg`` and can be accessed
    directly via corresponding Python attributes (e.g., ``node.name``):

        ``name`` (string)
            The name of the node, which corresponds to the ``[<name>]``
            section in ``node.cfg``.

        ``type`` (string)
            The type of the node, which will be one of ``standalone``,
            ``manager``, ``proxy``, and ``worker``.

        ``env_vars`` (string)
            A comma-separated list of environment variables to set when
            running Bro (e.g., ``env_vars=VAR1=1,VAR2=2``). These
            node-specific values override global values (specified in
            the ``broctl.cfg`` file).

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

        ``pin_cpus`` (string)
            A comma-separated list of CPU numbers to which the node's Bro
            processes will be pinned (if not specified, then CPU pinning will
            not be used for this node).  This option is only supported on
            Linux and FreeBSD (it is ignored on all other platforms).  CPU
            numbering starts at zero (e.g.,
            the only valid CPU numbers for a machine with one dual-core
            processor would be 0 and 1).  If the length of this list does not
            match the number of Bro processes for this node, then some CPUs
            could have zero (if too many CPU numbers are specified) or more
            than one (if not enough CPU numbers are specified) Bro processes
            pinned to them.  Only the specified CPU numbers will be used,
            regardless of whether additional CPU cores exist.

        ``aux_scripts`` (string)
            Any node-specific Bro script configured for this node.

        ``zone_id`` (string)
            If BroControl is managing a cluster comprised of nodes
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
    """

    # Valid keys in nodes file. The values will be stored in attributes of the
    # same name. Custom keys can be add via addKey().
    _keys = { "type": 1, "host": 1, "interface": 1, "aux_scripts": 1, 
              "brobase": 1, "ether": 1, "zone_id": 1,
              "lb_procs": 1, "lb_method": 1, "lb_interfaces": 1,
              "pin_cpus": 1, "env_vars": 1 }


    def __init__(self, name):
        """Instantiates a new node of the given name."""
        self.name = name

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
            elif type(v) == type({}):
                v = ",".join(["%s=%s" % (key, val) for (key, val) in sorted(v.items())])

            return v

        return ("%15s - " % self.name) + " ".join(["%s=%s" % (k, fmt(self.__dict__[k])) for k in sorted(self.__dict__.keys())])

    @doc.api
    def cwd(self):
        """Returns a string with the node's working directory."""
        return os.path.join(config.Config.spooldir, self.name)

    # Stores the nodes process ID.
    def setPID(self, pid):
        """Stores the process ID for the node's Bro process."""
        key = "%s-pid" % self.name
        config.Config._setState(key, str(pid))
        config.Config.appendStateVal(key)

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
        key = "%s-pid" % self.name
        config.Config._setState(key, "")
        config.Config.appendStateVal(key)

    def setCrashed(self):
        """Marks node's Bro process as having terminated unexpectedly."""
        key = "%s-crashed" % self.name
        config.Config._setState(key, "1")
        config.Config.appendStateVal(key)

    # Unsets the flag for unexpected termination.
    def clearCrashed(self):
        """Clears the mark for the node's Bro process having terminated
        unexpectedly."""
        key = "%s-crashed" % self.name
        config.Config._setState(key, "0")
        config.Config.appendStateVal(key)

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
