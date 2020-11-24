# Functions to read and access the zeekctl configuration.

import hashlib
import os
import socket
import subprocess
import re
import sys

from ZeekControl import py3zeek
from ZeekControl import node as node_mod
from ZeekControl import options
from ZeekControl.exceptions import ConfigurationError, RuntimeEnvironmentError
from .state import SqliteState
from .version import VERSION


# Class storing the zeekctl configuration.
#
# This class provides access to four types of configuration/state:
#
# - the global zeekctl configuration from zeekctl.cfg
# - the node configuration from node.cfg
# - dynamic state variables which are kept across restarts in spool/state.db

Config = None # Globally accessible instance of Configuration.

class NodeStore:
    def __init__(self):
        self.nodestore = {}
        self.nodenameslower = []

    def add_node(self, node):
        # Add a node to the nodestore, but first check for duplicate node
        # names. This check is not case-sensitive, because names are stored
        # lowercase in the state db, and some filesystems are not
        # case-sensitive (working dir name is node name).
        # Duplicate node names can occur either because the user defined two
        # nodes that differ only by case (e.g. "Worker-1" and "worker-1"), or
        # if a user defines a node name that conflicts with an auto-generated
        # one (e.g. "worker-1" with lb_procs=2 and "worker-1-2").
        namelower = node.name.lower()
        if namelower in self.nodenameslower:
            matchname = ""
            for nn in self.nodestore:
                if nn.lower() == namelower:
                    matchname = nn
                    break
            raise ConfigurationError('node name "%s" is a duplicate of "%s"' % (node.name, matchname))

        self.nodestore[node.name] = node
        self.nodenameslower.append(namelower)


class Configuration:
    def __init__(self, basedir, libdir, cfgfile, zeekscriptdir, ui, state=None):
        self.ui = ui
        self.basedir = basedir
        self.libdir = libdir
        self.cfgfile = cfgfile
        self.zeekscriptdir = zeekscriptdir
        global Config
        Config = self

        self.config = {}
        self.state = {}
        self.nodestore = {}

        self.localaddrs = self._get_local_addrs()

        # Read zeekctl.cfg.
        self.config = self._read_config(cfgfile)

        self._initialize_options()
        self._check_options()

        if state:
            self.state_store = state
        else:
            self.state_store = SqliteState(self.statefile)

        self.read_state()
        self._update_cfg_state()

    def reload_cfg(self):
        self.config = self._read_config(self.cfgfile)
        self._initialize_options()
        self._check_options()
        self._update_cfg_state()

    def _initialize_options(self):
        from ZeekControl import execute

        # Set defaults for options we get passed in.
        self.init_option("zeekbase", self.basedir)
        self.init_option("zeekscriptdir", self.zeekscriptdir)
        self.init_option("version", VERSION)
        self.init_option("libdir", self.libdir)

        # Initialize options that are not already set.
        errors = False
        for opt in options.options:
            if opt.dontinit:
                continue

            if opt.legacy_name:
                old_key = opt.legacy_name.lower()
                if old_key in self.config:
                    self.ui.error("option '%s' is no longer supported, please use '%s' instead" % (opt.legacy_name, opt.name))
                    errors = True
                    continue

            self.init_option(opt.name, opt.default)

        if errors:
            sys.exit(1)

        # Set defaults for options we derive dynamically.
        self.init_option("mailto", "%s" % os.getenv("USER"))
        self.init_option("mailfrom", "Zeek <zeek@%s>" % socket.gethostname())
        self.init_option("mailalarmsto", self.config["mailto"])

        # Determine operating system.
        success, output = execute.run_localcmd("uname")
        if not success or not output:
            raise RuntimeEnvironmentError("failed to run uname: %s" % output)
        self.init_option("os", output.strip())

        # Determine the CPU pinning command.
        pin_cmd = ""
        if self.config["os"] == "Linux":
            pin_cmd = "taskset -c"
        elif self.config["os"] == "FreeBSD":
            pin_cmd = "cpuset -l"

        self.init_option("pin_command", pin_cmd)

        # Find the time command (should be a GNU time for best results).
        time_cmd = ""
        success, output = execute.run_localcmd("which time")
        if success and output:
            # On redhat-based systems, path to cmd is prefixed with '\t' on 2nd
            # line when alias is defined.
            time_cmd = output.splitlines()[-1].strip()

        self.init_option("time", time_cmd)

        # Calculate the log expire interval (in minutes).
        minutes = self._get_interval_minutes("logexpireinterval")
        self.init_option("logexpireminutes", minutes)

    # Do a basic sanity check on zeekctl options.
    def _check_options(self):
        # Option names must be valid bash variable names because we will
        # write them to zeekctl-config.sh (note that zeekctl will convert "."
        # to "_" when it writes to zeekctl-config.sh).
        allowedchars = re.compile("^[a-z0-9_.]+$")
        nostartdigit = re.compile("^[^0-9]")

        for key, value in self.config.items():
            if re.match(allowedchars, key) is None:
                raise ConfigurationError('zeekctl option name "%s" contains invalid characters (allowed characters: a-z, 0-9, ., and _)' % key)
            if re.match(nostartdigit, key) is None:
                raise ConfigurationError('zeekctl option name "%s" cannot start with a number' % key)

            # No zeekctl option ever requires the entire value to be wrapped in
            # quotes, and since doing so can cause problems, we don't allow it.
            if isinstance(value, str):
                if (value.startswith('"') and value.endswith('"') or
                    value.startswith("'") and value.endswith("'")):
                    raise ConfigurationError('value of zeekctl option "%s" cannot be wrapped in quotes' % key)

        dirs = ("zeekbase", "logdir", "spooldir", "cfgdir", "zeekscriptdir",
                "bindir", "libdirinternal", "plugindir", "scriptsdir")
        files = ("makearchivename", )

        for d in dirs:
            v = self.config[d]
            if not os.path.isdir(v):
                raise ConfigurationError('zeekctl option "%s" directory not found: %s' % (d, v))

        for f in files:
            v = self.config[f]
            if not os.path.isfile(v):
                raise ConfigurationError('zeekctl option "%s" file not found: %s' % (f, v))

        # Verify that logs don't expire more quickly than the rotation interval
        logexpireseconds = 60 * self.config["logexpireminutes"]
        if 0 < logexpireseconds < self.config["logrotationinterval"]:
            raise ConfigurationError("Log expire interval cannot be shorter than the log rotation interval")


    # Convert a time interval string (from the value of the given option name)
    # to an integer number of minutes.
    def _get_interval_minutes(self, optname):
        # Conversion table for time units to minutes.
        units = {"day": 24*60, "hr": 60, "min": 1}

        ss = self.config[optname]
        try:
            # If no time unit, assume it's days (for backward compatibility).
            v = int(ss) * units["day"]
            return v
        except ValueError:
            pass

        # Time interval is a non-negative integer followed by an optional
        # space, followed by a time unit.
        mm = re.match("([0-9]+) ?(day|hr|min)s?$", ss)
        if mm is None:
            raise ConfigurationError('value of zeekctl option "%s" is invalid (value must be integer followed by a time unit "day", "hr", or "min"): %s' % (optname, ss))

        v = int(mm.group(1))
        v *= units[mm.group(2)]

        return v

    def initPostPlugins(self):
        # Read node.cfg
        self.nodestore = self._read_nodes()

        # If "env_vars" was specified in zeekctl.cfg, then apply to all nodes.
        varlist = self.config.get("env_vars")
        if varlist:
            try:
                global_env_vars = self._get_env_var_dict(varlist)
            except ConfigurationError as err:
                raise ConfigurationError("zeekctl config: %s" % err)

            for node in self.nodes():
                for (key, val) in global_env_vars.items():
                    # Values from node.cfg take precedence over zeekctl.cfg
                    node.env_vars.setdefault(key, val)

        # Check state store for any running nodes that are no longer in the
        # current node config.
        self._warn_dangling_zeek()

        # Set the standalone config option.
        standalone = len(self.nodestore) == 1

        self.init_option("standalone", standalone)

    # Provides access to the configuration options via the dereference operator.
    # Lookup the attribute in zeekctl options first, then in the dynamic state
    # variables.
    def __getattr__(self, attr):
        if attr in self.config:
            return self.config[attr]
        if attr in self.state:
            return self.state[attr]
        raise AttributeError("unknown config attribute %s" % attr)

    # Returns a sorted list of all zeekctl.cfg entries.
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
    # - By default (i.e. tag is None), all Nodes are returned.
    # - If tag is a node group name (e.g. "workers"), all nodes belonging to
    #   that group are returned.
    # - If tag is the name of a node, then that node is returned.
    def nodes(self, tag=None):
        nodetype = node_mod.group_type(tag)
        if nodetype == "_ALL_":
            tag = None

        nodes = []
        for n in self.nodestore.values():
            if nodetype == n.type or tag == n.name or tag is None:
                nodes += [n]

        nodes.sort(key=node_mod.sortnode)

        return nodes

    # Returns the manager Node (cluster config) or standalone Node (standalone
    # config).  Returns None if neither are available.
    def manager(self):
        if self.config["standalone"]:
            n = self.nodes()
        else:
            n = self.nodes(node_mod.manager_group())

        if not n:
            return None

        return n[0]

    def loggers(self):
        return self.nodes(node_mod.logger_group())

    def proxies(self):
        return self.nodes(node_mod.proxy_group())

    def workers(self):
        return self.nodes(node_mod.worker_group())

    # Returns a list of nodes which is a subset of the result a similar call to
    # nodes() would yield but within which each host appears only once.
    # If "exclude_local" is True, then the returned list will not include
    # nodes that are on the local host.
    def hosts(self, tag=None, exclude_local=False):
        hosts = {}
        nodelist = []
        for node in self.nodes(tag):
            if node.host in hosts:
                continue

            if exclude_local and node.addr in self.localaddrs:
                continue

            hosts[node.host] = 1
            nodelist.append(node)

        return nodelist

    # Replace all occurences of "${option}", with option being either
    # zeekctl.cfg option or a dynamic variable, with the corresponding value.
    # Defaults to replacement with the empty string for unknown options.
    def subst(self, text):
        while True:
            match = re.search(r"(\$\{([A-Za-z][A-Za-z0-9]*)(:([^}]+))?\})", text)
            if not match:
                return text

            key = match.group(2).lower()
            try:
                value = str(self.__getattr__(key))
            except AttributeError:
                value = match.group(4)
                if value is None:
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
            cpulist = [cpulist[i % cpulen] for i in range(numprocs)]

        return cpulist

    # Convert a string consisting of a comma-separated list of environment
    # variables (e.g. "VAR1=123, VAR2=456") to a dictionary.
    # If the string is empty, then return an empty dictionary.
    def _get_env_var_dict(self, text):
        env_vars = {}

        if text:
            for keyval in text.split(","):
                try:
                    key, val = keyval.split("=", 1)
                except ValueError:
                    raise ConfigurationError("missing '=' in env_vars option value: %s" % keyval)

                key = key.strip()
                if not key:
                    raise ConfigurationError("env_vars option value must contain at least one environment variable name: %s" % keyval)

                env_vars[key] = val.strip()

        return env_vars

    # Parse node.cfg.
    def _read_nodes(self):
        config = py3zeek.configparser.SafeConfigParser()
        fname = self.nodecfg
        try:
            if not config.read(fname):
                raise ConfigurationError("cannot read node config file: %s" % fname)
        except py3zeek.configparser.MissingSectionHeaderError as err:
            raise ConfigurationError(err)

        nodestore = NodeStore()

        counts = {}
        for sec in config.sections():
            node = node_mod.Node(self, sec)

            # Note that the keys are converted to lowercase by configparser.
            for (key, val) in config.items(sec):

                key = key.replace(".", "_")

                if key not in node_mod.Node._keys:
                    self.ui.warn("ignoring unrecognized node config option '%s' given for node '%s'" % (key, sec))
                    continue

                node.__dict__[key] = val

            # Perform a sanity check on the node, and update nodestore.
            self._check_node(node, nodestore, counts)

        # Perform a sanity check on the nodestore (make sure we have a valid
        # cluster config, etc.).
        self._check_nodestore(nodestore.nodestore)

        return nodestore.nodestore

    def _check_node(self, node, nodestore, counts):
        if not node.type:
            raise ConfigurationError("no type given for node %s" % node.name)

        if node.type not in node_mod.node_types():
            raise ConfigurationError("unknown node type '%s' given for node '%s'" % (node.type, node.name))

        if not node.host:
            raise ConfigurationError("no host given for node '%s'" % node.name)

        try:
            addrinfo = socket.getaddrinfo(node.host, None, 0, 0, socket.SOL_TCP)
        except socket.gaierror as e:
            raise ConfigurationError("hostname lookup failed for '%s' in node config [%s]" % (node.host, e.args[1]))

        addrs = [addr[4][0] for addr in addrinfo]

        # By default, just use the first IP addr in the list.
        addr_str = addrs[0]

        # Choose the first IPv4 addr (if any) in the list.
        for ip in addrs:
            if ":" not in ip:
                addr_str = ip
                break

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
            if not node_mod.is_worker(node):
                raise ConfigurationError("node '%s' config: load balancing node config options are only for worker nodes" % node.name)
            try:
                numprocs = int(node.lb_procs)
            except ValueError:
                raise ConfigurationError("number of load-balanced processes must be an integer for node '%s'" % node.name)
            if numprocs < 1:
                raise ConfigurationError("number of load-balanced processes must be greater than zero for node '%s'" % node.name)
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

            if node.lb_method not in ("pf_ring", "myricom", "custom", "interfaces"):
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

                # Update the node attrs that need to be changed
                newname = "%s-%d" % (origname, num)
                newnode.name = newname
                counts[node.type] += 1
                newnode.count = counts[node.type]
                if pin_cpus:
                    newnode.pin_cpus = pin_cpus[num-1]

                if newnode.lb_method == "interfaces":
                    newnode.interface = netifs.pop().strip()

                nodestore.add_node(newnode)

        nodestore.add_node(node)

    def _check_nodestore(self, nodestore):
        if not nodestore:
            raise ConfigurationError("no nodes found in node config")

        standalone = False
        manager = False
        proxy = False

        manageronlocalhost = False
        # Note: this is a subset of localaddrs
        localhostaddrs = "127.0.0.1", "::1"

        for n in nodestore.values():
            if node_mod.is_manager(n):
                if manager:
                    raise ConfigurationError("only one manager can be defined in node config")
                manager = True
                if n.addr in localhostaddrs:
                    manageronlocalhost = True

                if n.addr not in self.localaddrs:
                    raise ConfigurationError("must run zeekctl on same machine as the manager node. The manager node has IP address %s and this machine has IP addresses: %s" % (n.addr, ", ".join(self.localaddrs)))

            elif node_mod.is_proxy(n):
                proxy = True

            elif node_mod.is_standalone(n):
                standalone = True
                if n.addr not in self.localaddrs:
                    raise ConfigurationError("must run zeekctl on same machine as the standalone node. The standalone node has IP address %s and this machine has IP addresses: %s" % (n.addr, ", ".join(self.localaddrs)))

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
                if not node_mod.is_manager(n) and n.addr not in localhostaddrs:
                    raise ConfigurationError("all nodes must use localhost/127.0.0.1/::1 when manager uses it")


    def _to_bool(self, val):
        if val.lower() in ("1", "true"):
            return True
        if val.lower() in ("0", "false"):
            return False
        raise ValueError("invalid boolean: '%s'" % val)

    # Parses zeekctl.cfg and returns a dictionary of all entries.
    def _read_config(self, fname):
        type_converters = {"bool": self._to_bool, "int": int, "string": str}
        config = {}

        opt_names = set()
        for opt in options.options:
            # Convert key to lowercase because keys are stored in lowercase.
            key = opt.name.lower()
            opt_names.add(key)
            if opt.legacy_name:
                opt_names.add(opt.legacy_name.lower())

        with open(fname, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                args = line.split("=", 1)
                if len(args) != 2:
                    raise ConfigurationError("zeekctl config syntax error: %s" % line)

                key, val = args
                # Option names are not case-sensitive.
                key = key.strip().lower()

                # Warn about unrecognized options, but we can't check plugin
                # options here because no plugins have been loaded yet.
                if "." not in key and key not in opt_names:
                    self.ui.warn("ignoring unrecognized zeekctl option: %s" % key)
                    continue

                # if the key already exists, just overwrite with new value
                config[key] = val.strip()

        # Convert option values to correct data type
        for opt in options.options:
            # Convert key to lowercase because keys are stored in lowercase.
            key = opt.name.lower()
            if key in config:
                try:
                    config[key] = type_converters[opt.type](config[key])
                except ValueError:
                    raise ConfigurationError("zeekctl option '%s' has invalid value '%s' for type %s" % (key, config[key], opt.type))

        return config

    # Initialize a global option if not already set.
    def init_option(self, key, val):
        # Store option names in lowercase, because they are not case-sensitive.
        key = key.lower()

        if key not in self.config:
            if isinstance(val, str):
                self.config[key] = self.subst(val)
            else:
                self.config[key] = val

    # Set a global option (regardless of whether or not it is already set).
    def set_option(self, key, val):
        # Store option names in lowercase, because they are not case-sensitive.
        key = key.lower()

        self.config[key] = val

    # Returns value of an option, or None if the option is not defined.
    def get_option(self, key):
        # Convert key to lowercase because keys are stored in lowercase.
        return self.config.get(key.lower())

    # Set a dynamic state variable.
    def set_state(self, key, val):
        key = key.lower()
        if self.state.get(key) == val:
            return

        self.state[key] = val
        self.state_store.set(key, val)

    # Returns value of state variable, or the specified default value if the
    # state variable is not defined.
    def get_state(self, key, default=None):
        return self.state.get(key.lower(), default)

    # Read dynamic state variables.
    def read_state(self):
        self.state = dict(self.state_store.items())

    # Use the ifconfig command to find local IP addrs.
    def _get_local_addrs_ifconfig(self):
        try:
            # On Linux, ifconfig is often not in the user's standard PATH.
            # Also need to set LANG here to ensure that the output of ifconfig
            # is consistent regardless of which locale the system is using.
            proc = subprocess.Popen(["PATH=$PATH:/sbin:/usr/sbin LANG=C ifconfig", "-a"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            out, err = proc.communicate()
        except OSError:
            return False

        success = proc.returncode == 0
        if not success:
            return False

        localaddrs = []
        if py3zeek.using_py3:
            out = out.decode()

        # The output of ifconfig varies by OS and by IPv4 vs IPv6.
        # Linux example:
        #   inet addr:127.0.0.1
        #   inet6 addr: ::1/128
        # BSD (and OS X) example:
        #   inet 127.0.0.1
        #   inet6 ::1
        #   inet6 fe80::1%lo0
        for line in out.splitlines():
            fields = line.split()
            if len(fields) < 3:
                continue

            if fields[0] != "inet" and fields[0] != "inet6":
                continue

            addrstr = fields[1]

            if addrstr[-1] == ":" and addrstr.count(":") == 1:
                addrstr = fields[2]

            if addrstr.count(":") == 1:
                # Remove "addr:" prefix (if any).
                addrstr = addrstr.split(":")[1]

            # Remove everything after "/" or "%" (if any)
            addrstr = addrstr.split("/")[0]
            addrstr = addrstr.split("%")[0]

            if _is_valid_addr(addrstr):
                localaddrs.append(addrstr)

        if not localaddrs:
            self.ui.warn('failed to extract IP addresses from the "ifconfig -a" command output')

        return localaddrs

    # Use the ip command to find local IP addrs.
    def _get_local_addrs_ip(self):
        try:
            # On Linux, "ip" is sometimes not in the user's standard PATH.
            proc = subprocess.Popen(["PATH=$PATH:/sbin:/usr/sbin ip address"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            out, err = proc.communicate()
        except OSError:
            return False

        success = proc.returncode == 0
        if not success:
            return False

        localaddrs = []
        if py3zeek.using_py3:
            out = out.decode()

        # Here is an example portion of "ip" command output:
        #    inet 127.0.0.1/8
        #    inet6 ::1/128
        for line in out.splitlines():
            fields = line.split()
            if len(fields) < 2:
                continue

            if fields[0] != "inet" and fields[0] != "inet6":
                continue

            addrstr = fields[1]
            addrstr = addrstr.split("/")[0]
            addrstr = addrstr.split("%")[0]

            if _is_valid_addr(addrstr):
                localaddrs.append(addrstr)

        if not localaddrs:
            self.ui.warn('failed to extract IP addresses from the "ip address" command output')

        return localaddrs

    # Return a list of the IP addresses associated with local interfaces.
    # For IPv6 addresses, zone_id and prefix length are removed if present.
    def _get_local_addrs(self):
        # ifconfig is more portable so try it first
        localaddrs = self._get_local_addrs_ifconfig()

        if not localaddrs:
            # On some Linux systems ifconfig has been superseded by ip.
            localaddrs = self._get_local_addrs_ip()

        # Fallback to localhost if we did not find any IP addrs.
        if not localaddrs:
            self.ui.warn('failed to find local IP addresses with "ifconfig -a" or "ip address" commands')

            localaddrs = ["127.0.0.1", "::1"]
            try:
                addrinfo = socket.getaddrinfo(socket.gethostname(), None, 0, 0, socket.SOL_TCP)
            except Exception:
                addrinfo = []

            for ai in addrinfo:
                localaddrs.append(ai[4][0])

        return localaddrs

    # Record the Zeek version.
    def record_zeek_version(self):
        version = self._get_zeek_version()
        self.set_state("zeekversion", version)

    # Record the state of the zeekctl config files.
    def _update_cfg_state(self):
        self.set_state("configchksum", self._get_zeekctlcfg_hash(filehash=True))
        self.set_state("confignodechksum", self._get_nodecfg_hash(filehash=True))

    # Returns True if the zeekctl config files have changed since last reload.
    def is_cfg_changed(self):
        try:
            if "configchksum" in self.state:
                if self.state["configchksum"] != self._get_zeekctlcfg_hash(filehash=True):
                    return True

            if "confignodechksum" in self.state:
                if self.state["confignodechksum"] != self._get_nodecfg_hash(filehash=True):
                    return True
        except IOError:
            # If we can't read the config files, then do nothing.
            pass

        return False

    # Check if the user has already run the "install" or "deploy" commands.
    def is_zeekctl_installed(self):
        return os.path.isfile(os.path.join(self.config["policydirsiteinstallauto"], "zeekctl-config.zeek"))

    # Warn user to run zeekctl deploy if any changes are detected to zeekctl
    # config options, node config, Zeek version, or if certain state variables
    # are missing.
    def warn_zeekctl_install(self):
        missingstate = False

        # Check if node config has changed since last install.
        if "hash-nodecfg" in self.state:
            nodehash = self._get_nodecfg_hash()

            if nodehash != self.state["hash-nodecfg"]:
                self.ui.warn('zeekctl node config has changed (run the zeekctl "deploy" command)')

                return
        else:
            missingstate = True

        # If this is a fresh install (i.e., zeekctl install not yet run), then
        # inform the user what to do.
        if not self.is_zeekctl_installed():
            self.ui.info('Hint: Run the zeekctl "deploy" command to get started.')
            return

        # Check if Zeek version is different from the previously-installed
        # version.
        if "zeekversion" in self.state:
            oldversion = self.state["zeekversion"]

            version = self._get_zeek_version()

            if version != oldversion:
                self.ui.warn('new zeek version detected (run the zeekctl "deploy" command)')
                return
        else:
            missingstate = True

        # Check if any config values have changed since last install.
        if "hash-zeekctlcfg" in self.state:
            cfghash = self._get_zeekctlcfg_hash()
            if cfghash != self.state["hash-zeekctlcfg"]:
                self.ui.warn('zeekctl config has changed (run the zeekctl "deploy" command)')
                return
        else:
            missingstate = True

        # If any of the state variables don't exist, then we need to install
        # (this would most likely indicate an upgrade install was performed
        # over an old version that didn't have the state.db file).
        if missingstate:
            self.ui.warn('state database needs updating (run the zeekctl "deploy" command)')
            return

    # Warn if there might be any dangling Zeek nodes (i.e., nodes that are
    # still running but are either no longer part of the current node
    # configuration or have moved to a new host).
    def _warn_dangling_zeek(self):
        nodes = {}
        for n in self.nodes():
            # Convert node name to lowercase because below we are using
            # node names from the state db (which is lowercase).
            nodes[n.name.lower()] = n.host

        for key in self.state.keys():
            # Look for a PID associated with a Zeek node
            if not key.endswith("-pid"):
                continue

            pid = self.get_state(key)
            if not pid:
                continue

            # Get node name and host name for this node
            nname = key[:-4]
            hostkey = key.replace("-pid", "-host")
            hname = self.get_state(hostkey)
            if not hname:
                continue

            # If node is not a known node or if host has changed, then
            # we must warn about dangling Zeek node.
            if nname not in nodes or hname != nodes[nname]:
                self.ui.warn('Zeek node "%s" possibly still running on host "%s" (PID %s)' % (nname, hname, pid))
                # Set the "expected running" flag to False so cron doesn't try
                # to start this node.
                expectkey = key.replace("-pid", "-expect-running")
                self.set_state(expectkey, False)
                # Clear the PID so we don't keep getting warnings.
                self.set_state(key, None)

    # Return a hash value (as a string) of the current zeekctl configuration.
    def _get_zeekctlcfg_hash(self, filehash=False):
        if filehash:
            with open(self.cfgfile, "r") as ff:
                data = ff.read()
        else:
            data = str(sorted(self.config.items()))

        if py3zeek.using_py3:
            data = data.encode()

        hh = hashlib.sha1()
        hh.update(data)
        return hh.hexdigest()

    # Return a hash value (as a string) of the current zeekctl node config.
    def _get_nodecfg_hash(self, filehash=False):
        if filehash:
            with open(self.nodecfg, "r") as ff:
                data = ff.read()
        else:
            nn = []
            for n in self.nodes():
                nn.append(tuple([(key, val) for key, val in n.items() if not key.startswith("_")]))
            data = str(nn)

        if py3zeek.using_py3:
            data = data.encode()

        hh = hashlib.sha1()
        hh.update(data)
        return hh.hexdigest()

    # Update the stored hash value of the current zeekctl config.
    def update_cfg_hash(self):
        cfghash = self._get_zeekctlcfg_hash()
        nodehash = self._get_nodecfg_hash()

        self.set_state("hash-zeekctlcfg", cfghash)
        self.set_state("hash-nodecfg", nodehash)

    # Runs Zeek to get its version number.
    def _get_zeek_version(self):
        from ZeekControl import execute

        zeek = self.config["zeek"]
        if not os.path.lexists(zeek):
            raise ConfigurationError("cannot find Zeek binary: %s" % zeek)

        version = ""
        success, output = execute.run_localcmd("%s -v" % zeek)
        if success and output:
            version = output.splitlines()[-1]
        else:
            msg = " with no output"
            if output:
                msg = " with output:\n%s" % output
            raise RuntimeEnvironmentError('running "zeek -v" failed%s' % msg)

        match = re.search(".* version ([^ ]*).*$", version)
        if not match:
            raise RuntimeEnvironmentError('cannot determine Zeek version ("zeek -v" output: %s)' % version.strip())

        version = match.group(1)
        # If zeek is built with the "--enable-debug" configure option, then it
        # appends "-debug" to the version string.
        if version.endswith("-debug"):
            version = version[:-6]

        return version


# Check if a string is a valid representation of an IP address or not.
def _is_valid_addr(ipstr):
    try:
        if ":" in ipstr:
            socket.inet_pton(socket.AF_INET6, ipstr)
        else:
            socket.inet_pton(socket.AF_INET, ipstr)
    except socket.error:
        return False

    return True

