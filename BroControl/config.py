# Functions to read and access the broctl configuration.

import os
import socket
import re
import copy
import ConfigParser

import execute
import node as node_mod
import options
import plugin
import util

from .state import SqliteState
from .version import VERSION

# Class storing the broctl configuration.
#
# This class provides access to four types of configuration/state:
#
# - the global broctl configuration from broctl.cfg
# - the node configuration from node.cfg
# - dynamic state variables which are kept across restarts in spool/broctl.dat

Config = None # Globally accessible instance of Configuration.

class ConfigurationError(Exception):
    pass

def sqlite_state_factory(config):
    return SqliteState(config.statefile)

class Configuration:
    def __init__(self, basedir, cmdout, state_factory=sqlite_state_factory):
        config_file = os.path.join(BroCfgDir, "etc", "broctl.cfg")
        broscriptdir = os.path.join(basedir, "share/bro")
        global Config
        Config = self

        self.config = {}
        self.state = {}

        # Read broctl.cfg.
        self.config = self._readConfig(config, cmdout)
        if self.config is None:
            raise RuntimeError

        # Set defaults for options we get passed in.
        self._setOption("brobase", basedir)
        self._setOption("broscriptdir", broscriptdir)
        self._setOption("version", VERSION)

        # Initialize options.
        for opt in options.options:
            if not opt.dontinit:
                self._setOption(opt.name, opt.default)

        self.state_store = state_factory(self)

        # Set defaults for options we derive dynamically.
        self._setOption("mailto", "%s" % os.getenv("USER"))
        self._setOption("mailfrom", "Big Brother <bro@%s>" % socket.gethostname())
        self._setOption("mailalarmsto", self.config["mailto"])

        # Determine operating system.
        (success, output) = execute.runLocalCmd("uname")
        if not success:
            raise RuntimeError("cannot run uname")
        self._setOption("os", output[0].lower().strip())

        if self.config["os"] == "linux":
            self._setOption("pin_command", "taskset -c")
        elif self.config["os"] == "freebsd":
            self._setOption("pin_command", "cpuset -l")
        else:
            self._setOption("pin_command", "")

        # Find the time command (should be a GNU time for best results).
        (success, output) = execute.runLocalCmd("which time")
        if success:
            self._setOption("time", output[0].lower().strip())
        else:
            self._setOption("time", "")

    def initPostPlugins(self, cmdout):
        plugin.Registry.addNodeKeys()

        # Read node.cfg and broctl.dat.
        if not self._readNodes(cmdout):
            return False
        if not self.readState(cmdout):
            return False

        # If "env_vars" was specified in broctl.cfg, then apply to all nodes.
        varlist = self.config.get("env_vars")
        if varlist:
            try:
                global_env_vars = self._getEnvVarDict(varlist)
            except ValueError, err:
                raise ConfigurationError("env_vars option in broctl.cfg: %s" % err)

            for node in self.nodes("all"):
                for (key, val) in global_env_vars.items():
                    # Values from node.cfg take precedence over broctl.cfg
                    node.env_vars.setdefault(key, val)

        # Now that the nodes have been read in, set the standalone config option.
        standalone = "0"
        for node in self.nodes("all"):
            if node.type == "standalone":
                standalone = "1"

        self._setOption("standalone", standalone)

        # Make sure cron flag is cleared.
        self.config["cron"] = "0"

        return True

    # Provides access to the configuration options via the dereference operator.
    # Lookups the attribute in broctl.cfg first, then in the dynamic variables
    # from broctl.dat.
    # Defaults to empty string for unknown options.
    def __getattr__(self, attr):
        if attr in self.config:
            return self.config[attr]
        if attr in self.state:
            return self.state[attr]
        return ""

    # Returns True if attribute is defined.
    def hasAttr(self, attr):
        if attr in self.config:
            return True
        if attr in self.state:
            return True
        return False

    # Returns a list of all broctl.cfg entries.
    # Includes dynamic variables if dynamic is true.
    def options(self, dynamic=True):
        if dynamic:
            return self.config.items() + self.state.items()
        else:
            return self.config.items()

    # Returns a list of Nodes (the list will be empty if no matching nodes
    # are found).  The returned list is sorted by node type, and by node name
    # for each type.
    # - If tag is None, all Nodes are returned.
    # - If tag is "all", all Nodes are returned if "expand_all" is true.
    #     If "expand_all" is false, returns an empty list in this case.
    # - If tag is "proxies", all proxy Nodes are returned.
    # - If tag is "workers", all worker Nodes are returned.
    # - If tag is "manager", the manager Node is returned (cluster config) or
    #     the standalone Node is returned (standalone config).
    # - If tag is "standalone", the standalone Node is returned.
    # - If tag is the name of a node, then that node is returned.
    def nodes(self, tag=None, expand_all=True):
        nodes = []
        type = None

        if tag == "all":
            if not expand_all:
                return []

            tag = None

        elif tag == "standalone":
            type = "standalone"

        elif tag == "manager":
            type = "manager"

        elif tag == "proxies":
            type = "proxy"

        elif tag == "workers":
            type = "worker"

        for n in self.nodelist.values():
            if type:
                if type == n.type:
                    nodes += [n]

            elif tag == n.name or not tag:
                nodes += [n]

        nodes.sort(key=lambda n: (n.type, n.name))

        if not nodes and tag == "manager":
            nodes = self.nodes("standalone")

        return nodes

    # Returns the manager Node (cluster config) or standalone Node (standalone
    # config).
    def manager(self):
        n = self.nodes("manager")
        if n:
            return n[0]
        n = self.nodes("standalone")
        if n:
            return n[0]
        return None

    # Returns a list of nodes which is a subset of the result a similar call to
    # nodes() would yield but within which each host appears only once.
    def hosts(self, tag = None):
        hosts = {}
        nodelist = []
        for node in self.nodes(tag):
            if node.host not in hosts:
                hosts[node.host] = 1
                nodelist.append(node)

        return nodelist

    # Replace all occurences of "${option}", with option being either
    # broctl.cfg option or a dynamic variable, with the corresponding value.
    # Defaults to replacement with the empty string for unknown options.
    def subst(self, str):
        while True:
            m = re.search(r"(\$\{([A-Za-z]+)(:([^}]+))?\})", str)
            if not m:
                return str

            key = m.group(2).lower()
            if self.hasAttr(key):
                value = self.__getattr__(key)
            else:
                value = m.group(4)

            if not value:
                value = ""

            str = str[0:m.start(1)] + value + str[m.end(1):]


    # Convert string into list of integers (ValueError is raised if any
    # item in the list is not a non-negative integer).
    def _getPinCPUList(self, str, numprocs):
        if not str:
            return []

        cpulist = map(int, str.split(","))
        # Minimum allowed CPU number is zero.
        if min(cpulist) < 0:
            raise ValueError

        # Make sure list is at least as long as number of worker processes.
        cpulen = len(cpulist)
        if numprocs > cpulen:
            cpulist = [ cpulist[i % cpulen] for i in xrange(numprocs) ]

        return cpulist

    # Convert a string consisting of a comma-separated list of environment
    # variables (e.g. "VAR1=123, VAR2=456") to a dictionary.
    # If the string is empty, then return an empty dictionary.  Upon error,
    # a ValueError is raised.
    def _getEnvVarDict(self, str):
        env_vars = {}

        if str:
            # If the entire string is quoted, then remove only those quotes.
            if (str.startswith('"') and str.endswith('"')) or (str.startswith("'") and str.endswith("'")):
                str = str[1:-1]

        if str:
            for keyval in str.split(","):
                try:
                    (key, val) = keyval.split("=", 1)
                except ValueError:
                    raise ConfigurationError("missing '=' after environment variable name")

                if not key.strip():
                    raise ConfigurationError("missing environment variable name")

                env_vars[key.strip()] = val.strip()

        return env_vars

    # Parse node.cfg.
    def _readNodes(self, cmdout):
        self.nodelist = {}
        config = ConfigParser.SafeConfigParser()
        if not config.read(self.nodecfg):
            raise ConfigurationError("cannot read '%s'" % self.nodecfg)

        manager = False
        proxy = False
        worker = False
        standalone = False

        file = self.nodecfg

        counts = {}
        for sec in config.sections():
            node = node_mod.Node(self, sec)
            self.nodelist[sec] = node

            for (key, val) in config.items(sec):

                key = key.replace(".", "_")

                if key not in node_mod.Node._keys:
                    cmdout.warn("%s: unknown key '%s' in section '%s'" % (file, key, sec))
                    continue

                if key == "type":
                    if val == "manager":
                        if manager:
                            cmdout.error("only one manager can be defined")
                            return False
                        manager = True

                    elif val == "proxy":
                        proxy = True

                    elif val == "worker":
                        worker = True

                    elif val == "standalone":
                        standalone = True

                    else:
                        raise ConfigurationError("%s: unknown type '%s' in section '%s'" % (file, val, sec))


                node.__dict__[key] = val

            # Convert env_vars from a string to a dictionary.
            try:
                node.env_vars = self._getEnvVarDict(node.env_vars)
            except ValueError, err:
                raise ConfigurationError("%s: section %s: %s" % (file, sec, err))

            try:
                addrinfo = socket.getaddrinfo(node.host, None, 0, 0, socket.SOL_TCP)
                if len(addrinfo) == 0:
                    raise ConfigurationError("%s: no addresses resolved in section '%s' for host %s" % (file, sec, node.host))

                addr_str = addrinfo[0][4][0]
                # zone_id is handled manually, so strip it if it's there
                node.addr = addr_str.split('%')[0]
            except AttributeError:
                raise ConfigurationError("%s: no host given in section '%s'" % (file, sec))
            except socket.gaierror, e:
                raise ConfigurationError("%s: unknown host '%s' in section '%s' [%s]" % (file, node.host, sec, e.args[1]))

            # Each node gets a number unique across its type.
            type = self.nodelist[sec].type
            try:
                counts[type] += 1
            except KeyError:
                counts[type] = 1

            node.count = counts[type]

            numprocs = 0

            if node.lb_procs:
                try:
                    numprocs = int(node.lb_procs)
                    if numprocs < 1:
                        raise ConfigurationError("%s: value of lb_procs must be at least 1 in section '%s'" % (file, sec))
                except ValueError:
                    raise ConfigurationError("%s: value of lb_procs must be an integer in section '%s'" % (file, sec))
            elif node.lb_method:
                raise ConfigurationError("%s: load balancing requires lb_procs in section '%s'" % (file, sec))

            try:
                pin_cpus = self._getPinCPUList(node.pin_cpus, numprocs)
            except ValueError:
                raise ConfigurationError("%s: pin_cpus must be list of non-negative integers in section '%s'" % (file, sec))

            if pin_cpus:
                node.pin_cpus = pin_cpus[0]

            if node.lb_procs:
                if not node.lb_method:
                    raise ConfigurationError("%s: no load balancing method given in section '%s'" % (file, sec))

                if node.lb_method not in ("pf_ring", "myricom", "interfaces"):
                    raise ConfigurationError("%s: unknown load balancing method given in section '%s'" % (file, sec))

                if node.lb_method == "interfaces":
                    if not node.lb_interfaces:
                        raise ConfigurationError("%s: no list of interfaces given in section '%s'" % (file, sec))
                        return False

                    # get list of interfaces to use, and assign one to each node
                    netifs = node.lb_interfaces.split(",")

                    if len(netifs) != int(node.lb_procs):
                        raise ConfigurationError("%s: number of interfaces does not match value of lb_procs in section '%s'" % (file, sec))

                    node.interface = netifs.pop().strip()

                # node names will have a numerical suffix
                node.name = "%s-1" % sec

                for num in xrange(2, numprocs + 1):
                    newnode = copy.deepcopy(node)
                    # only the node name, count, and pin_cpus need to be changed
                    newname = "%s-%d" % (sec, num)
                    newnode.name = newname
                    self.nodelist[newname] = newnode
                    counts[type] += 1
                    newnode.count = counts[type]
                    if pin_cpus:
                        newnode.pin_cpus = pin_cpus[num-1]

                    if newnode.lb_method == "interfaces":
                        newnode.interface = netifs.pop().strip()

        if self.nodelist:

            if not standalone:
                if not manager:
                    raise ConfigurationError("%s: no manager defined" % file)

                if not proxy:
                    raise ConfigurationError("%s: no proxy defined" % file)

            else:
                if len(self.nodelist) > 1:
                    raise ConfigurationError("%s: more than one node defined in stand-alone setup" % file)

        manageronlocalhost = False

        for n in self.nodelist.values():
            if not n.name:
                raise ConfigurationError("node configured without a name")

            if not n.host:
                raise ConfigurationError("no host given for node %s" % n.name)

            if not n.type:
                raise ConfigurationError("no type given for node %s" % n.name)

            if n.type == "manager":
                if not execute.isLocal(n, cmdout):
                    raise ConfigurationError("script must be run on manager node")

                if ( n.addr == "127.0.0.1" or n.addr == "::1" ) and n.type != "standalone":
                    manageronlocalhost = True

        # If manager is on localhost, then all other nodes must be on localhost
        if manageronlocalhost:
            for n in self.nodelist.values():
                if n.type != "manager" and n.type != "standalone":
                    if n.addr != "127.0.0.1" and n.addr != "::1":
                        raise ConfigurationError("cannot use localhost/127.0.0.1/::1 for manager host in nodes configuration")

        return True


    # Parses broctl.cfg or broctl.dat and returns a dictionary of all entries.
    def _readConfig(self, file, cmdout, allowstate = False):
        config = {}
        for line in open(file):

            line = line.strip()
            if not line or line.startswith("#"):
                continue

            args = line.split("=", 1)
            if len(args) != 2:
                raise ConfigurationError("%s: syntax error '%s'" % (file, line))

            (key, val) = args
            key = key.strip().lower()
            val = val.strip()

            if not allowstate and ".state." in key:
                raise ConfigurationError("state variable '%s' not allowed in file: %s" % (key, file))

            # if the key already exists, just overwrite with new value
            config[key] = val

        return config

    # Initialize a global option if not already set.
    def _setOption(self, key, val):
        if key not in self.config:
            self.config[key] = self.subst(val)

    # Set a dynamic state variable.
    def _setState(self, key, val):
        self.state[key] = val
        self.state_store.sete(key, val)

    def _getState(self, key):
        return self.state_store.get(key)

    # Read dynamic state variables from {$spooldir}/broctl.dat .
    def readState(self, cmdout):
        self.state = dict(self.state_store.items())
        if self.state is None:
            return False

        return True

    # Write the dynamic state variables into {$spooldir}/broctl.dat .
    def writeState(self, cmdout):
        pass

    # Append the given dynamic state variable to {$spooldir}/broctl.dat .
    def appendStateVal(self, key):
        pass

    # Record the Bro version.
    def determineBroVersion(self, cmdout):
        version = self._getBroVersion(cmdout)
        if not version:
            return False

        self.state["broversion"] = version
        self.state["bro"] = self.subst("${bindir}/bro")
        return True


    # Warn user to run broctl install if any config changes are detected.
    def warnBroctlInstall(self, cmdout):
        # Check if Bro version is different from previously-installed version.
        if "broversion" in self.state:
            oldversion = self.state["broversion"]

            version = self._getBroVersion(cmdout)
            if not version:
                return False

            if version != oldversion:
                cmdout.warn("new bro version detected (run the broctl \"restart --clean\" or \"install\" command)")
                return True

        # Check if node config has changed since last install.
        if "hash-nodecfg" in self.state:
            nodehash = self.getNodeCfgHash()

            if nodehash != self.state["hash-nodecfg"]:
                cmdout.warn("broctl node config has changed (run the broctl \"restart --clean\" or \"install\" command)")
                return True

        # Check if any config values have changed since last install.
        if "hash-broctlcfg" in self.state:
            cfghash = self.getBroctlCfgHash()
            if cfghash != self.state["hash-broctlcfg"]:
                cmdout.warn("broctl config has changed (run the broctl \"restart --clean\" or \"install\" command)")
                return True

        return True


    # Return a hash value (as a string) of the current broctl configuration.
    def getBroctlCfgHash(self):
        return str(hash(tuple(sorted(self.config.items()))))

    # Update the stored hash value of the current broctl configuration.
    def updateBroctlCfgHash(self):
        cfghash = self.getBroctlCfgHash()
        self._setState("hash-broctlcfg", cfghash)

    # Return a hash value (as a string) of the current broctl node config.
    def getNodeCfgHash(self):
        nn = []
        for n in self.nodes():
            nn.append(tuple(n.items()))
        return str(hash(tuple(nn)))

    # Update the stored hash value of the current broctl node config.
    def updateNodeCfgHash(self):
        nodehash = self.getNodeCfgHash()
        self._setState("hash-nodecfg", nodehash)

    # Runs Bro to get its version numbers.
    def _getBroVersion(self, cmdout):
        version = ""
        bro = self.subst("${bindir}/bro")
        if execute.exists(None, bro, cmdout):
            (success, output) = execute.runLocalCmd("%s -v" % bro)
            if success and output:
                version = output[-1]
        else:
            cmdout.error("cannot find Bro binary to determine version")
            return None

        m = re.search(".* version ([^ ]*).*$", version)
        if not m:
            cmdout.error("cannot determine Bro version [%s]" % version.strip())
            return None

        version = m.group(1)
        # If bro is built with the "--enable-debug" configure option, then it
        # appends "-debug" to the version string.
        if version.endswith("-debug"):
            version = version[:-6]

        return version

