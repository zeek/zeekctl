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

# Class storing the broctl configuration.
#
# This class provides access to four types of configuration/state:
#
# - the global broctl configuration from broctl.cfg
# - the node configuration from node.cfg
# - dynamic state variables which are kept across restarts in spool/broctl.dat

Config = None # Globally accessible instance of Configuration.

class Configuration:
    def __init__(self, config, basedir, broscriptdir, version):
        global Config
        Config = self

        self.config = {}
        self.state = {}

        # Read broctl.cfg.
        self.config = self._readConfig(config)

        # Set defaults for options we get passed in.
        self._setOption("brobase", basedir)
        self._setOption("broscriptdir", broscriptdir)
        self._setOption("version", version)

        # Initialize options.
        for opt in options.options:
            if not opt.dontinit:
                self._setOption(opt.name, opt.default)

        # Set defaults for options we derive dynamically.
        self._setOption("mailto", "%s" % os.getenv("USER"))
        self._setOption("mailfrom", "Big Brother <bro@%s>" % socket.gethostname())
        self._setOption("home", os.getenv("HOME"))
        self._setOption("mailalarmsto", self.config["mailto"])

        # Determine operating system.
        (success, output) = execute.runLocalCmd("uname")
        if not success:
            util.error("cannot run uname")
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

    def initPostPlugins(self):
        plugin.Registry.addNodeKeys()

        # Read node.cfg and broctl.dat.
        self._readNodes()
        self.readState()

        # If "env_vars" was specified in broctl.cfg, then apply to all nodes.
        varlist = self.config.get("env_vars")
        if varlist:
            try:
                global_env_vars = self._getEnvVarDict(varlist)
            except ValueError, err:
                util.error("broctl.cfg: %s" % err)

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

    # Provides access to the configuration options via the dereference operator.
    # Lookups the attribute in broctl.cfg first, then in the dynamic variables from broctl.dat.
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
    # are found).
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
        for node in self.nodes(tag):
            if not node.host in hosts:
                hosts[node.host] = node

        return hosts.values()

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
                    raise ValueError("missing '=' after environment variable name")

                if not key.strip():
                    raise ValueError("missing environment variable name")

                env_vars[key.strip()] = val.strip()

        return env_vars

    # Parse node.cfg.
    def _readNodes(self):
        self.nodelist = {}
        config = ConfigParser.SafeConfigParser()
        if not config.read(self.nodecfg):
            util.error("cannot read '%s'" % self.nodecfg)

        manager = False
        proxy = False
        worker = False
        standalone = False

        file = self.nodecfg

        counts = {}
        for sec in config.sections():
            node = node_mod.Node(sec)
            self.nodelist[sec] = node

            for (key, val) in config.items(sec):

                key = key.replace(".", "_")

                if not key in node_mod.Node._keys:
                    util.warn("%s: unknown key '%s' in section '%s'" % (file, key, sec))
                    continue

                if key == "type":
                    if val == "manager":
                        if manager:
                            util.error("only one manager can be defined")
                        manager = True

                    elif val == "proxy":
                        proxy = True

                    elif val == "worker":
                        worker = True

                    elif val == "standalone":
                        standalone = True

                    else:
                        util.error("%s: unknown type '%s' in section '%s'" % (file, val, sec))


                node.__dict__[key] = val

            # Convert env_vars from a string to a dictionary.
            try:
                node.env_vars = self._getEnvVarDict(node.env_vars)
            except ValueError, err:
                util.error("%s: section %s: %s" % (file, sec, err))

            try:
                addrinfo = socket.getaddrinfo(node.host, None, 0, 0, socket.SOL_TCP)
                if len(addrinfo) == 0:
                    util.error("%s: no addresses resolved in section '%s' for host %s" % (file, sec, node.host))

                addr_str = addrinfo[0][4][0]
                # zone_id is handled manually, so strip it if it's there
                node.addr = addr_str.split('%')[0]
            except AttributeError:
                util.error("%s: no host given in section '%s'" % (file, sec))
            except socket.gaierror, e:
                util.error("%s: unknown host '%s' in section '%s' [%s]" % (file, node.host, sec, e.args[1]))

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
                        util.error("%s: value of lb_procs must be at least 1 in section '%s'" % (file, sec))
                except ValueError:
                    util.error("%s: value of lb_procs must be an integer in section '%s'" % (file, sec))
            elif node.lb_method:
                util.error("%s: load balancing requires lb_procs in section '%s'" % (file, sec))

            try:
                pin_cpus = self._getPinCPUList(node.pin_cpus, numprocs)
            except ValueError:
                util.error("%s: pin_cpus must be list of non-negative integers in section '%s'" % (file, sec))

            if pin_cpus:
                node.pin_cpus = pin_cpus[0]

            if node.lb_procs:
                if not node.lb_method:
                    util.error("%s: no load balancing method given in section '%s'" % (file, sec))

                if node.lb_method not in ("pf_ring", "myricom", "interfaces"):
                    util.error("%s: unknown load balancing method given in section '%s'" % (file, sec))

                if node.lb_method == "interfaces":
                    if not node.lb_interfaces:
                        util.error("%s: no list of interfaces given in section '%s'" % (file, sec))

                    # get list of interfaces to use, and assign one to each node
                    netifs = node.lb_interfaces.split(",")

                    if len(netifs) != int(node.lb_procs):
                        util.error("%s: number of interfaces does not match value of lb_procs in section '%s'" % (file, sec))

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
                    util.error("%s: no manager defined" % file)

                if not proxy:
                    util.error("%s: no proxy defined" % file)

            else:
                if len(self.nodelist) > 1:
                    util.error("%s: more than one node defined in stand-alone setup" % file)

        manageronlocalhost = False

        for n in self.nodelist.values():
            if not n.name:
                util.error("node configured without a name")

            if not n.host:
                util.error("no host given for node %s" % n.name)

            if not n.type:
                util.error("no type given for node %s" % n.name)

            if n.type == "manager":
                if not execute.isLocal(n):
                    util.error("script must be run on manager node")

                if ( n.addr == "127.0.0.1" or n.addr == "::1" ) and n.type != "standalone":
                    manageronlocalhost = True

        # If manager is on localhost, then all other nodes must be on localhost
        if manageronlocalhost:
            for n in self.nodelist.values():
                if n.type != "manager" and n.type != "standalone":
                    if n.addr != "127.0.0.1" and n.addr != "::1":
                        util.error("cannot use localhost/127.0.0.1/::1 for manager host in nodes configuration")

    # Parses broctl.cfg or broctl.dat and returns a dictionary of all entries.
    def _readConfig(self, file, allowstate = False):
        config = {}
        try:
            for line in open(file):

                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                args = line.split("=", 1)
                if len(args) != 2:
                    util.error("%s: syntax error '%s'" % (file, line))

                (key, val) = args
                key = key.strip().lower()
                val = val.strip()

                if not allowstate and ".state." in key:
                    util.error("state variable '%s' not allowed in file: %s" % (key, file))

                # if the key already exists, just overwrite with new value
                config[key] = val

        except IOError, e:
            util.warn("cannot read '%s' (this is ok on first run)" % file)

        return config

    # Initialize a global option if not already set.
    def _setOption(self, val, key):
        val = val.lower()
        if not val in self.config:
            self.config[val] = self.subst(key)

    # Set a dynamic state variable.
    def _setState(self, val, key):
        val = val.lower()
        self.state[val] = key

    # Read dynamic state variables from {$spooldir}/broctl.dat .
    def readState(self):
        self.state = self._readConfig(self.statefile, True)

    # Write the dynamic state variables into {$spooldir}/broctl.dat .
    def writeState(self):
        tmpstatefile = self.statefile + ".tmp"
        try:
            out = open(tmpstatefile, "w")
        except IOError:
            util.warn("can't write '%s'" % self.statefile)
            return

        print >>out, "# Automatically generated. Do not edit.\n"

        for (key, val) in self.state.items():
            print >>out, "%s = %s" % (key, self.subst(str(val)))

        out.close()

        # update state file in an atomic operation
        os.rename(tmpstatefile, self.statefile)

    # Append the given dynamic state variable to {$spooldir}/broctl.dat .
    def appendStateVal(self, key):
        key = key.lower()

        try:
            out = open(self.statefile, "a")
        except IOError:
            util.warn("can't append to '%s'" % self.statefile)
            return

        print >>out, "%s = %s" % (key, self.state[key])

        out.close()

    # Record the Bro version.
    def determineBroVersion(self):
        version = self._getBroVersion()
        self.state["broversion"] = version
        self.state["bro"] = self.subst("${bindir}/bro")


    # Check if the Bro version is different from previously-installed version.
    def checkBroVersion(self):
        if "broversion" not in self.state:
            return

        oldversion = self.state["broversion"]

        version = self._getBroVersion()
        if version != oldversion:
            util.warn("new bro version detected (run 'broctl install')")


    # Runs Bro to get its version numbers.
    def _getBroVersion(self):
        version = ""
        bro = self.subst("${bindir}/bro")
        if execute.exists(None, bro):
            (success, output) = execute.runLocalCmd("%s -v" % bro)
            if success and output:
                version = output[-1]
        else:
            util.error("cannot find Bro binary to determine version")

        m = re.search(".* version ([^ ]*).*$", version)
        if not m:
            util.error("cannot determine Bro version [%s]" % version.strip())

        version = m.group(1)
        # If bro is built with the "--enable-debug" configure option, then it
        # appends "-debug" to the version string.
        if version.endswith("-debug"):
            version = version[:-6]

        return version

