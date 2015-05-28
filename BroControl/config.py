# Functions to read and access the broctl configuration.

import os
import socket
import re
import zlib

from BroControl import py3bro
from BroControl import node as node_mod
from BroControl import options
from .state import SqliteState
from .version import VERSION


# Class storing the broctl configuration.
#
# This class provides access to four types of configuration/state:
#
# - the global broctl configuration from broctl.cfg
# - the node configuration from node.cfg
# - dynamic state variables which are kept across restarts in spool/state.db

Config = None # Globally accessible instance of Configuration.

class ConfigurationError(Exception):
    pass

class Configuration:
    def __init__(self, basedir, cfgfile, broscriptdir, ui, localaddrs=[], state=None):
        self.ui = ui
        self.localaddrs = localaddrs
        global Config
        Config = self

        self.config = {}
        self.state = {}
        self.nodestore = {}

        # Read broctl.cfg.
        self.config = self._read_config(cfgfile)

        self._initialize_options(basedir, broscriptdir)
        self._check_options()

        if state:
            self.state_store = state
        else:
            self.state_store = SqliteState(self.statefile)


    def _initialize_options(self, basedir, broscriptdir):
        from BroControl import execute

        # Set defaults for options we get passed in.
        self._set_option("brobase", basedir)
        self._set_option("broscriptdir", broscriptdir)
        self._set_option("version", VERSION)

        # Initialize options that are not already set.
        for opt in options.options:
            if not opt.dontinit:
                self._set_option(opt.name, opt.default)

        # Set defaults for options we derive dynamically.
        self._set_option("mailto", "%s" % os.getenv("USER"))
        self._set_option("mailfrom", "Big Brother <bro@%s>" % socket.gethostname())
        self._set_option("mailalarmsto", self.config["mailto"])

        # Determine operating system.
        (success, output) = execute.run_localcmd("uname")
        if not success:
            raise RuntimeError("cannot run uname")
        self._set_option("os", output[0].lower().strip())

        if self.config["os"] == "linux":
            self._set_option("pin_command", "taskset -c")
        elif self.config["os"] == "freebsd":
            self._set_option("pin_command", "cpuset -l")
        else:
            self._set_option("pin_command", "")

        # Find the time command (should be a GNU time for best results).
        (success, output) = execute.run_localcmd("which time")
        if success:
            self._set_option("time", output[0].lower().strip())
        else:
            self._set_option("time", "")


    # Do a basic sanity check on some critical options.
    def _check_options(self):
        dirs = ("brobase", "logdir", "spooldir", "cfgdir", "broscriptdir", "bindir", "libdirinternal", "plugindir", "scriptsdir")
        files = ("makearchivename", )

        for d in dirs:
            v = self.config[d]
            if not os.path.isdir(v):
                raise ConfigurationError('broctl option "%s" directory not found: %s' % (d, v))

        for f in files:
            v = self.config[f]
            if not os.path.isfile(v):
                raise ConfigurationError('broctl option "%s" file not found: %s' % (f, v))

    def initPostPlugins(self):
        self.read_state()

        # Read node.cfg
        self.nodestore = self._read_nodes()

        # If "env_vars" was specified in broctl.cfg, then apply to all nodes.
        varlist = self.config.get("env_vars")
        if varlist:
            try:
                global_env_vars = self._get_env_var_dict(varlist)
            except ConfigurationError as err:
                raise ConfigurationError("broctl config: %s" % err)

            for node in self.nodes("all"):
                for (key, val) in global_env_vars.items():
                    # Values from node.cfg take precedence over broctl.cfg
                    node.env_vars.setdefault(key, val)

        # Set the standalone config option.
        standalone = "0"
        if len(self.nodestore) == 1:
            standalone = "1"

        self._set_option("standalone", standalone)

        # Make sure cron flag is cleared.
        self.config["cron"] = "0"

    # Provides access to the configuration options via the dereference operator.
    # Lookup the attribute in broctl options first, then in the dynamic state
    # variables.
    def __getattr__(self, attr):
        if attr in self.config:
            return self.config[attr]
        if attr in self.state:
            return self.state[attr]
        raise AttributeError("unknown config attribute %s" % attr)

    # Returns True if attribute is defined.
    def has_attr(self, attr):
        if attr in self.config:
            return True
        if attr in self.state:
            return True
        return False

    # Returns a sorted list of all broctl.cfg entries.
    # Includes dynamic variables if dynamic is true.
    def options(self, dynamic=True):
        optlist = list(self.config.items())
        if dynamic:
            optlist += list(self.state.items())

        optlist.sort()
        return optlist

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
        nodetype = None

        if tag == "all":
            if not expand_all:
                return []

            tag = None

        elif tag == "standalone":
            nodetype = "standalone"

        elif tag == "manager":
            nodetype = "manager"

        elif tag == "proxies":
            nodetype = "proxy"

        elif tag == "workers":
            nodetype = "worker"

        for n in self.nodestore.values():
            if nodetype:
                if nodetype == n.type:
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
    # If "nolocal" parameter is True, then exclude the local host from results.
    def hosts(self, tag=None, nolocal=False):
        hosts = {}
        nodelist = []
        for node in self.nodes(tag):
            if node.host in hosts:
                continue

            if (not nolocal) or (nolocal and node.addr not in self.localaddrs):
                hosts[node.host] = 1
                nodelist.append(node)

        return nodelist

    # Replace all occurences of "${option}", with option being either
    # broctl.cfg option or a dynamic variable, with the corresponding value.
    # Defaults to replacement with the empty string for unknown options.
    def subst(self, text):
        while True:
            match = re.search(r"(\$\{([A-Za-z]+)(:([^}]+))?\})", text)
            if not match:
                return text

            key = match.group(2).lower()
            if self.has_attr(key):
                value = self.__getattr__(key)
            else:
                value = match.group(4)

            if not value:
                value = ""

            text = text[0:match.start(1)] + value + text[match.end(1):]


    # Convert string into list of integers (ValueError is raised if any
    # item in the list is not a non-negative integer).
    def _get_pin_cpu_list(self, text, numprocs):
        if not text:
            return []

        cpulist = [int(x) for x in text.split(",")]
        # Minimum allowed CPU number is zero.
        if min(cpulist) < 0:
            raise ValueError

        # Make sure list is at least as long as number of worker processes.
        cpulen = len(cpulist)
        if numprocs > cpulen:
            cpulist = [ cpulist[i % cpulen] for i in range(numprocs) ]

        return cpulist

    # Convert a string consisting of a comma-separated list of environment
    # variables (e.g. "VAR1=123, VAR2=456") to a dictionary.
    # If the string is empty, then return an empty dictionary.
    def _get_env_var_dict(self, text):
        env_vars = {}

        if text:
            for keyval in text.split(","):
                try:
                    (key, val) = keyval.split("=", 1)
                except ValueError:
                    raise ConfigurationError("missing '=' in env_vars option: %s" % keyval)

                key = key.strip()
                if not key:
                    raise ConfigurationError("missing environment variable name in env_vars option: %s" % keyval)

                env_vars[key] = val.strip()

        return env_vars

    # Parse node.cfg.
    def _read_nodes(self):
        config = py3bro.configparser.SafeConfigParser()
        fname = self.nodecfg
        try:
            if not config.read(fname):
                raise ConfigurationError("cannot read node config file: %s" % fname)
        except py3bro.configparser.MissingSectionHeaderError as err:
            raise ConfigurationError(err)

        nodestore = {}

        counts = {}
        for sec in config.sections():
            node = node_mod.Node(self, sec)

            for (key, val) in config.items(sec):

                key = key.replace(".", "_")

                if key not in node_mod.Node._keys:
                    self.ui.warn("ignoring unrecognized node config option '%s' given for node '%s'" % (key, sec))
                    continue

                node.__dict__[key] = val

            self._check_node(node, nodestore, counts)

            if node.name in nodestore:
                raise ConfigurationError("duplicate node name '%s'" % node.name)
            nodestore[node.name] = node

        self._check_nodestore(nodestore)
        return nodestore

    def _check_node(self, node, nodestore, counts):
        if not node.type:
            raise ConfigurationError("no type given for node %s" % node.name)

        if node.type not in ("manager", "proxy", "worker", "standalone"):
            raise ConfigurationError("unknown node type '%s' given for node '%s'" % (node.type, node.name))

        if not node.host:
            raise ConfigurationError("no host given for node '%s'" % node.name)

        try:
            addrinfo = socket.getaddrinfo(node.host, None, 0, 0, socket.SOL_TCP)
        except socket.gaierror as e:
            raise ConfigurationError("unknown host '%s' given for node '%s' [%s]" % (node.host, node.name, e.args[1]))

        addr_str = addrinfo[0][4][0]
        # zone_id is handled manually, so strip it if it's there
        node.addr = addr_str.split("%")[0]

        # Convert env_vars from a string to a dictionary.
        try:
            node.env_vars = self._get_env_var_dict(node.env_vars)
        except ConfigurationError as err:
            raise ConfigurationError("node '%s' config: %s" % (node.name, err))

        # Each node gets a number unique across its type.
        try:
            counts[node.type] += 1
        except KeyError:
            counts[node.type] = 1

        node.count = counts[node.type]

        numprocs = 0

        if node.lb_procs:
            if node.type != "worker":
                raise ConfigurationError("load balancing node config options are only for worker nodes")
            try:
                numprocs = int(node.lb_procs)
            except ValueError:
                raise ConfigurationError("number of load-balanced processes must be an integer for node '%s'" % node.name)
            if numprocs < 2:
                raise ConfigurationError("number of load-balanced processes must be at least 2 for node '%s'" % node.name)
        elif node.lb_method:
            raise ConfigurationError("number of load-balanced processes not specified for node '%s'" % node.name)

        try:
            pin_cpus = self._get_pin_cpu_list(node.pin_cpus, numprocs)
        except ValueError:
            raise ConfigurationError("pin cpus list must contain only non-negative integers for node '%s'" % node.name)

        if pin_cpus:
            node.pin_cpus = pin_cpus[0]

        if node.lb_procs:
            if not node.lb_method:
                raise ConfigurationError("no load balancing method given for node '%s'" % node.name)

            if node.lb_method not in ("pf_ring", "myricom", "interfaces"):
                raise ConfigurationError("unknown load balancing method '%s' given for node '%s'" % (node.lb_method, node.name))

            if node.lb_method == "interfaces":
                if not node.lb_interfaces:
                    raise ConfigurationError("list of load-balanced interfaces not specified for node '%s'" % node.name)

                # get list of interfaces to use, and assign one to each node
                netifs = node.lb_interfaces.split(",")

                if len(netifs) != numprocs:
                    raise ConfigurationError("number of load-balanced interfaces is not same as number of load-balanced processes for node '%s'" % node.name)

                node.interface = netifs.pop().strip()

            origname = node.name
            # node names will have a numerical suffix
            node.name = "%s-1" % node.name

            for num in range(2, numprocs + 1):
                newnode = node.copy()
                # only the node name, count, and pin_cpus need to be changed
                newname = "%s-%d" % (origname, num)
                newnode.name = newname
                if newname in nodestore:
                    raise ConfigurationError("duplicate node name '%s'" % newname)
                nodestore[newname] = newnode
                counts[node.type] += 1
                newnode.count = counts[node.type]
                if pin_cpus:
                    newnode.pin_cpus = pin_cpus[num-1]

                if newnode.lb_method == "interfaces":
                    newnode.interface = netifs.pop().strip()

    def _check_nodestore(self, nodestore):
        if not nodestore:
            raise ConfigurationError("no nodes found in node config")

        standalone = False
        manager = False
        proxy = False

        manageronlocalhost = False

        for n in nodestore.values():
            if n.type == "manager":
                if manager:
                    raise ConfigurationError("only one manager can be defined")
                manager = True
                if n.addr in ("127.0.0.1", "::1"):
                    manageronlocalhost = True

                if n.addr not in self.localaddrs:
                    raise ConfigurationError("must run broctl only on manager node")

            elif n.type == "proxy":
                proxy = True

            elif n.type == "standalone":
                standalone = True

        if standalone:
            if len(nodestore) > 1:
                raise ConfigurationError("more than one node defined in standalone node config")
        else:
            if not manager:
                raise ConfigurationError("no manager defined in node config")
            elif not proxy:
                raise ConfigurationError("no proxy defined in node config")

        # If manager is on localhost, then all other nodes must be on localhost
        if manageronlocalhost:
            for n in nodestore.values():
                if n.type != "manager" and n.addr not in ("127.0.0.1", "::1"):
                    raise ConfigurationError("cannot use localhost/127.0.0.1/::1 for manager host in node config")


    # Parses broctl.cfg and returns a dictionary of all entries.
    def _read_config(self, fname):
        config = {}
        with open(fname, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                args = line.split("=", 1)
                if len(args) != 2:
                    raise ConfigurationError("broctl config syntax error: %s" % line)

                (key, val) = args
                key = key.strip().lower()

                # if the key already exists, just overwrite with new value
                config[key] = val.strip()

        return config

    # Initialize a global option if not already set.
    def _set_option(self, key, val):
        key = key.lower()
        if key not in self.config:
            self.config[key] = self.subst(val)

    # Set a dynamic state variable.
    def set_state(self, key, val):
        key = key.lower()
        self.state[key] = val
        self.state_store.set(key, val)

    # Returns value of state variable, or None if it's not defined.
    def get_state(self, key):
        return self.state.get(key)

    # Read dynamic state variables.
    def read_state(self):
        self.state = dict(self.state_store.items())

    # Record the Bro version.
    def record_bro_version(self):
        version = self._get_bro_version()
        self.set_state("broversion", version)
        self.set_state("bro", self.subst("${bindir}/bro"))


    # Warn user to run broctl install if any changes are detected to broctl
    # config options, node config, Bro version, or if certain state variables
    # are missing.  If the "isinstall" parameter is True, then we're running
    # the install or deploy command, so some of the warnings are skipped.
    def warn_broctl_install(self, isinstall):
        missingstate = False

        # Check if node config has changed since last install.
        if "hash-nodecfg" in self.state:
            nodehash = self._get_nodecfg_hash()

            if nodehash != self.state["hash-nodecfg"]:
                # If running the install/deploy cmd, then skip this warning
                if not isinstall:
                    self.ui.warn("broctl node config has changed (run the broctl \"deploy\" command)")

                self._warn_dangling_bro()
                return
        else:
            missingstate = True

        # If we're running the install or deploy commands, then skip the
        # rest of the checks.
        if isinstall:
            return

        freshinstall = not os.path.exists(os.path.join(self.config["scriptsdir"], "broctl-config.sh"))

        # If this is a fresh install (i.e., broctl install not yet run), then
        # inform the user what to do.
        if freshinstall:
            self.ui.info("Hint: Run the broctl \"deploy\" command to get started.")
            return

        # Check if Bro version is different from the previously-installed
        # version.
        if "broversion" in self.state:
            oldversion = self.state["broversion"]

            version = self._get_bro_version()

            if version != oldversion:
                self.ui.warn("new bro version detected (run the broctl \"deploy\" command)")
                return
        else:
            missingstate = True

        # Check if any config values have changed since last install.
        if "hash-broctlcfg" in self.state:
            cfghash = self._get_broctlcfg_hash()
            if cfghash != self.state["hash-broctlcfg"]:
                self.ui.warn("broctl config has changed (run the broctl \"deploy\" command)")
                return
        else:
            missingstate = True

        # If any of the state variables don't exist, then we need to install
        # (this would most likely indicate an upgrade install was performed
        # over an old version that didn't have the state.db file).
        if missingstate:
            self.ui.warn("state database needs updating (run the broctl \"deploy\" command)")
            return

    # Warn if there might be any dangling Bro nodes (i.e., nodes that are
    # no longer part of the current node configuration, but that are still
    # running).
    def _warn_dangling_bro(self):
        nodes = [ n.name for n in self.nodes() ]

        for key in self.state.keys():
            # Check if a PID is defined for a Bro node
            if key.endswith("-pid") and self.get_state(key):
                nn = key[:-4]
                # Check if node name is in list of all known nodes
                if nn not in nodes:
                    hostkey = key.replace("-pid", "-host")
                    hname = self.get_state(hostkey)
                    if hname:
                        self.ui.warn("Bro node \"%s\" possibly still running on host \"%s\" (PID %s)" % (nn, hname, self.get_state(key)))

    # Return a hash value (as a string) of the current broctl configuration.
    def _get_broctlcfg_hash(self):
        data = str(sorted(self.config.items()))
        if py3bro.using_py3:
            data = data.encode()
        # The "bitwise AND" ensures the same result on any python version.
        return str(zlib.crc32(data) & 0xffffffff)

    # Update the stored hash value of the current broctl configuration.
    def update_broctlcfg_hash(self):
        cfghash = self._get_broctlcfg_hash()
        self.set_state("hash-broctlcfg", cfghash)

    # Return a hash value (as a string) of the current broctl node config.
    def _get_nodecfg_hash(self):
        nn = []
        for n in self.nodes():
            nn.append(tuple([(key, val) for key, val in n.items() if not key.startswith("_")]))
        data = str(nn)
        if py3bro.using_py3:
            data = data.encode()
        # The "bitwise AND" ensures the same result on any python version.
        return str(zlib.crc32(data) & 0xffffffff)

    # Update the stored hash value of the current broctl node config.
    def update_nodecfg_hash(self):
        nodehash = self._get_nodecfg_hash()
        self.set_state("hash-nodecfg", nodehash)

    # Runs Bro to get its version number.
    def _get_bro_version(self):
        from BroControl import execute

        bro = self.subst("${bindir}/bro")
        if not os.path.lexists(bro):
            raise ConfigurationError("cannot find Bro binary: %s" % bro)

        version = ""
        (success, output) = execute.run_localcmd("%s -v" % bro)
        if success and output:
            version = output[-1]
        else:
            msg = ""
            if output:
                msg = " with output:\n%s" % "\n".join(output)
            raise ConfigurationError("running \"bro -v\" failed%s" % msg)

        match = re.search(".* version ([^ ]*).*$", version)
        if not match:
            raise ConfigurationError("cannot determine Bro version [%s]" % version.strip())

        version = match.group(1)
        # If bro is built with the "--enable-debug" configure option, then it
        # appends "-debug" to the version string.
        if version.endswith("-debug"):
            version = version[:-6]

        return version

