# Functions to read and access the broctl configuration.

import os
import sys
import socket
import imp
import re
import copy

import ConfigParser

import doc
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
    def __init__(self, config, basedir, version):
        global Config
        Config = self

        self.config = {}
        self.state = {}

        # Read broctl.cfg.
        self.config = self._readConfig(config)

        # Set defaults for options we get passed in.
        self._setOption("brobase", basedir)
        self._setOption("version", version)

        # Initialize options.
        for opt in options.options:
            if not opt.dontinit:
                self._setOption(opt.name.lower(), opt.default)

        # Set defaults for options we derive dynamically.
        self._setOption("mailto", "%s" % os.getenv("USER"))
        self._setOption("mailfrom", "Big Brother <bro@%s>" % socket.gethostname())
        self._setOption("home", os.getenv("HOME"))
        self._setOption("mailalarmsto", self.config["mailto"])

        # Determine operating system.
        (success, output) = execute.captureCmd("uname")
        if not success:
            util.error("cannot run uname")
        self._setOption("os", output[0].lower().strip())

        # Find the time command (should be a GNU time for best results).
        (success, output) = execute.captureCmd("which time")
        self._setOption("time", output[0].lower().strip())

    def initPostPlugins(self):
        plugin.Registry.addNodeKeys()

        # Read node.cfg and broctl.dat.
        self._readNodes()
        self.readState()

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

    # Returns a list of Nodes.
    # - If tag is "global" or "all", all Nodes are returned if "expand_all" is true.
    #     If "expand_all" is false, returns an empty list in this case.
    # - If tag is "proxies" or "proxy", all proxy Nodes are returned.
    # - If tag is "workers" or "worker", all worker Nodes are returned.
    # - If tag is "manager", the manager Node is returned.
    def nodes(self, tag=None, expand_all=True):
        nodes = []
        type = None

        if tag == "cluster" or tag == "all":
            if not expand_all:
                return []

            tag = None

        elif tag == "proxies":
            type = "proxy"

        elif tag == "workers":
            type = "worker"

        elif tag in self.config:
            type = tag

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

    # Returns the manager Node.
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

            if node.lb_procs:
                try:
                    numprocs = int(node.lb_procs)
                    if numprocs < 1:
                        util.error("%s: value of lb_procs must be at least 1 in section '%s'" % (file, sec))
                except ValueError:
                    util.error("%s: value of lb_procs must be an integer in section '%s'" % (file, sec))

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

                for num in xrange(2, int(node.lb_procs) + 1):
                    newnode = copy.deepcopy(node)
                    # only the node name and count need to be changed
                    newname = "%s-%d" % (sec, num)
                    newnode.name = newname
                    self.nodelist[newname] = newnode
                    counts[type] += 1
                    newnode.count = counts[type]

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
                    util.error("cannot use localhost/127.0.0.1/::1 for manager host in nodes configuration")

    # Parses broctl.cfg and returns a dictionary of all entries.
    def _readConfig(self, file):
        config = {}
        try:
            for line in open(file):

                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                args = line.split("=")
                if len(args) != 2:
                    util.error("%s: syntax error '%s'" % (file, line))

                (key, val) = args
                key = key.strip().lower()
                val = val.strip()

                config[key] = val

        except IOError, e:
            util.warn("cannot read '%s' (this is ok on first run)" % file)

        return config

    # Initialize a global option if not already set.
    def _setOption(self, val, key):
        if not val in self.config:
            self.config[val] = self.subst(key)

    # Set a dynamic state variable.
    def _setState(self, val, key):
        val = val.lower()
        self.state[val] = key

    # Read dynamic state variables from {$spooldir}/broctl.dat .
    def readState(self):
        self.state = self._readConfig(self.statefile)

    # Write the dynamic state variables into {$spooldir}/broctl.dat .
    def writeState(self):
        try:
            out = open(self.statefile, "w")
        except IOError:
            util.warn("can't write '%s'" % self.statefile)
            return

        print >>out, "# Automatically generated. Do not edit.\n"

        for (key, val) in self.state.items():
            print >>out, "%s = %s" % (key, self.subst(str(val)))

    # Runs Bro to get its version numbers.
    def determineBroVersion(self):
        version = None
        bro = self.subst("${bindir}/bro")
        if execute.exists(None, bro):
            (success, output) = execute.captureCmd("%s -v 2>&1" % bro)
            if success:
                version = output[len(output)-1]

        if not version:
            # Ok if it's already set.
            if "broversion" in self.state:
                return

            util.error("cannot find Bro binary to determine version")

        m = re.search(".* version ([^ ]*).*$", version)
        if not m:
            util.error("cannot determine Bro version [%s]" % version.strip())

        version = m.group(1)
        if version.endswith("-debug"):
            version = version[:-6]

        self.state["broversion"] = version
        self.state["bro"] = self.subst("${bindir}/bro")

