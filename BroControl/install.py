# Functions to install files on all nodes.

import os

from BroControl import util
from BroControl import config
from BroControl import py3bro

# In all paths given in this file, ${<option>} will replaced with the value of
# the corresponding configuration option.

# Directories/files in form (path, mirror) which are synced from the manager to
# all remote hosts.
# If "mirror" is False, then the path is assumed to be a directory and it will
# just be created on the remote host.  If "mirror" is True, then the path
# is fully mirrored recursively.
def get_syncs():
    syncs = [
    ("${brobase}", False),
    ("${brobase}/share", True),
    ("${cfgdir}", True),
    ("${libdir}", True),
    ("${bindir}", True),
    ("${policydirsiteinstall}", True),
    ("${policydirsiteinstallauto}", True),
    # ("${policydir}", True),
    # ("${staticdir}", True),
    ("${logdir}", False),
    ("${spooldir}", False),
    ("${tmpdir}", False),
    ("${broctlconfigdir}/broctl-config.sh", True)
    ]

    return syncs

# In NFS-mode, only these will be synced.
def get_nfssyncs():
    nfssyncs = [
    ("${spooldir}", False),
    ("${tmpdir}", False),
    ("${policydirsiteinstall}", True),
    ("${policydirsiteinstallauto}", True),
    ("${broctlconfigdir}/broctl-config.sh", True)
    ]

    return nfssyncs

# Generate a shell script "broctl-config.sh" that sets env. vars. that
# correspond to broctl config options.
def make_broctl_config_sh(cmdout):
    ostr = ""
    for (varname, value) in config.Config.options(dynamic=False):
        if isinstance(value, bool):
            # Convert bools to the string "1" or "0"
            value = "1" if value else "0"
        else:
            value = str(value)

        # In order to prevent shell errors, here we convert plugin
        # option names to use underscores, and double quotes in the value
        # are escaped.
        ostr += '%s="%s"\n' % (varname.replace(".", "_"), value.replace('"', '\\"'))

    # Rather than just overwriting the file, we first write out a tmp file,
    # and then rename it to avoid a race condition where a process outside of
    # broctl (such as archive-log) is trying to read the file while it is
    # being written.
    cfg_path = os.path.join(config.Config.broctlconfigdir, "broctl-config.sh")
    tmp_path = os.path.join(config.Config.broctlconfigdir, ".broctl-config.sh.tmp")

    try:
        with open(tmp_path, "w") as out:
            out.write(ostr)
    except IOError as e:
        cmdout.error("failed to write file: %s" % e)
        return False

    try:
        os.rename(tmp_path, cfg_path)
    except OSError as e:
        cmdout.error("failed to rename file %s: %s" % (tmp_path, e))
        return False

    symlink = os.path.join(config.Config.scriptsdir, "broctl-config.sh")

    # check if the symlink needs to be updated
    try:
        update_link = not os.path.islink(symlink) or os.readlink(symlink) != cfg_path
    except OSError as e:
        cmdout.error("failed to read symlink: %s" % e)
        return False

    if update_link:
        # attempt to update the symlink
        try:
            util.force_symlink(cfg_path, symlink)
        except OSError as e:
            cmdout.error("failed to update symlink '%s' to point to '%s': %s" % (symlink, cfg_path, e.strerror))
            return False

    return True


class Logger:
    # The "loggers" parameter is a list of logger nodes.
    def __init__(self, loggers):
        self.loggerlist = [ll.name for ll in loggers]
        self._ct = 0
        self._template_str = '$logger="%s", '
        # This is the most recently used logger (empty string if no loggers).
        self.logger = ""

    # Return a string containing the name of the next logger (at end of list,
    # return first logger in the list).  If the list of loggers is empty, then
    # just return the most recently used one (which might be an empty string).
    def next_logger(self):
        num = len(self.loggerlist)
        if num:
            self.logger = self._template_str % self.loggerlist[self._ct % num]
            self._ct += 1
        return self.logger


# Create Bro-side broctl configuration file.
def make_layout(path, cmdout, silent=False):
    class Port:
        def __init__(self, startport):
            # This is the first port number to use.
            self.p = startport

        # Record the port number that the specified node will use (if node is
        # None, then don't record it) and return that port number.
        def use_port(self, node):
            port = self.p
            # Increment the port number, since we're using the current one.
            self.p += 1

            if node is not None:
                node.setPort(port)

            return port

    manager = config.Config.manager()
    broport = Port(config.Config.broport)

    if config.Config.nodes("standalone"):
        if not silent:
            cmdout.info("generating standalone-layout.bro ...")

        filename = os.path.join(path, "standalone-layout.bro")

        ostr = "# Automatically generated. Do not edit.\n"
        # This is the port that standalone nodes listen on for remote
        # control by default.
        ostr += "redef Communication::listen_port = %s/tcp;\n" % broport.use_port(manager)
        ostr += "redef Communication::nodes += {\n"
        ostr += '\t["control"] = [$host=%s, $zone_id="%s", $class="control", $events=Control::controller_events],\n' % (util.format_bro_addr(manager.addr), manager.zone_id)
        ostr += "};\n"

    else:
        if not silent:
            cmdout.info("generating cluster-layout.bro ...")

        filename = os.path.join(path, "cluster-layout.bro")
        workers = config.Config.nodes("workers")
        proxies = config.Config.nodes("proxies")
        loggers = config.Config.nodes("loggers")

        mylogger = Logger(loggers)

        # If no loggers are defined, then manager does the logging.
        manager_is_logger = "F" if loggers else "T"

        ostr = "# Automatically generated. Do not edit.\n"
        ostr += "redef Cluster::manager_is_logger = %s;\n" % manager_is_logger
        ostr += "redef Cluster::nodes = {\n"

        # Control definition.  For now just reuse the manager information.
        ostr += '\t["control"] = [$node_type=Cluster::CONTROL, $ip=%s, $zone_id="%s", $p=%s/tcp],\n' % (util.format_bro_addr(manager.addr), config.Config.zoneid, broport.use_port(None))

        # Loggers definition
        for lognode in loggers:
            ostr += '\t["%s"] = [$node_type=Cluster::LOGGER, $ip=%s, $zone_id="%s", $p=%s/tcp],\n' % (lognode.name, util.format_bro_addr(lognode.addr), lognode.zone_id, broport.use_port(lognode))

        # Manager definition
        ostr += '\t["%s"] = [$node_type=Cluster::MANAGER, $ip=%s, $zone_id="%s", $p=%s/tcp, %s$workers=set(' % (manager.name, util.format_bro_addr(manager.addr), manager.zone_id, broport.use_port(manager), mylogger.next_logger())
        ostr += ", ".join('"%s"' % s.name for s in workers)
        ostr += ")],\n"

        # Proxies definition (all proxies use same logger as the manager)
        for p in proxies:
            ostr += '\t["%s"] = [$node_type=Cluster::PROXY, $ip=%s, $zone_id="%s", $p=%s/tcp, %s$manager="%s", $workers=set(' % (p.name, util.format_bro_addr(p.addr), p.zone_id, broport.use_port(p), mylogger.logger, manager.name)
            ostr += ", ".join('"%s"' % s.name for s in workers)
            ostr += ")],\n"

        # Workers definition
        for w in workers:
            p = w.count % len(proxies)
            ostr += '\t["%s"] = [$node_type=Cluster::WORKER, $ip=%s, $zone_id="%s", $p=%s/tcp, $interface="%s", %s$manager="%s", $proxy="%s"],\n' % (w.name, util.format_bro_addr(w.addr), w.zone_id, broport.use_port(w), w.interface, mylogger.next_logger(), manager.name, proxies[p].name)

        # Activate time-machine support if configured.
        if config.Config.timemachinehost:
            ostr += '\t["time-machine"] = [$node_type=Cluster::TIME_MACHINE, $ip=%s, $p=%s],\n' % (config.Config.timemachinehost, config.Config.timemachineport)

        ostr += "};\n"

    try:
        with open(filename, "w") as out:
            out.write(ostr)
    except IOError as e:
        cmdout.error("failed to write file: %s" % e)
        return False

    return True


# Reads in a list of networks from file.
def read_networks(fname):

    nets = []

    with open(fname, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            fields = line.split(None, 1)

            cidr = util.format_bro_prefix(fields[0])
            tag = fields[1] if len(fields) == 2 else ""

            nets += [(cidr, tag)]

    return nets


# Create Bro script which contains a list of local networks.
def make_local_networks(path, cmdout):

    netcfg = config.Config.localnetscfg

    try:
        nets = read_networks(netcfg)
    except IndexError:
        cmdout.error("invalid CIDR notation in file: %s" % netcfg)
        return False
    except IOError as e:
        cmdout.error("failed to read file: %s" % e)
        return False

    ostr = "# Automatically generated. Do not edit.\n\n"

    ostr += "redef Site::local_nets = {\n"
    for (cidr, tag) in nets:
        ostr += "\t%s," % cidr
        if tag:
            ostr += "\t# %s" % tag
        ostr += "\n"
    ostr += "};\n\n"

    try:
        with open(os.path.join(path, "local-networks.bro"), "w") as out:
            out.write(ostr)
    except IOError as e:
        cmdout.error("failed to write file: %s" % e)
        return False

    return True


def make_broctl_config_policy(path, cmdout, plugin_reg):
    manager = config.Config.manager()

    ostr = '# Automatically generated. Do not edit.\n'
    ostr += 'redef Notice::mail_dest = "%s";\n' % config.Config.mailto
    ostr += 'redef Notice::mail_dest_pretty_printed = "%s";\n' % config.Config.mailalarmsto
    ostr += 'redef Notice::sendmail = "%s";\n' % config.Config.sendmail
    ostr += 'redef Notice::mail_subject_prefix = "%s";\n' % config.Config.mailsubjectprefix
    ostr += 'redef Notice::mail_from = "%s";\n' % config.Config.mailfrom
    if manager.type != "standalone":
        loggers = config.Config.nodes("loggers")
        ntype = "LOGGER" if loggers else "MANAGER"
        ostr += '@if ( Cluster::local_node_type() == Cluster::%s )\n' % ntype

    ostr += 'redef Log::default_rotation_interval = %s secs;\n' % config.Config.logrotationinterval
    ostr += 'redef Log::default_mail_alarms_interval = %s secs;\n' % config.Config.mailalarmsinterval

    if manager.type != "standalone":
        ostr += '@endif\n'

    if config.Config.ipv6comm:
        ostr += 'redef Communication::listen_ipv6 = T;\n'
    else:
        ostr += 'redef Communication::listen_ipv6 = F;\n'

    ostr += 'redef Pcap::snaplen = %s;\n' % config.Config.pcapsnaplen
    ostr += 'redef Pcap::bufsize = %s;\n' % config.Config.pcapbufsize

    seed_str = make_global_hash_seed()
    ostr += 'redef global_hash_seed = "%s";\n' % seed_str

    ostr += plugin_reg.getBroctlConfig()

    filename = os.path.join(path, "broctl-config.bro")
    try:
        with open(filename, "w") as out:
            out.write(ostr)
    except IOError as e:
        cmdout.error("failed to write file: %s" % e)
        return False

    return True


# Create a new random seed value if one is not found in the state database (this
# ensures a consistent value after a restart).  Return a string representation.
def make_global_hash_seed():
    seed_str = config.Config.get_state("global-hash-seed")

    if not seed_str:
        # Get 4 bytes of random data (Bro uses 4 bytes to create an initial seed
        # in the Hasher::MakeSeed() function if global_hash_seed is an empty string).
        seed = os.urandom(4)

        # Convert each byte of seed value to a two-character hex string.
        if py3bro.using_py3:
            seed_str = "".join(["%02x" % i for i in seed])
        else:
            seed_str = "".join(["%02x" % ord(s) for s in seed])

        config.Config.set_state("global-hash-seed", seed_str)

    return seed_str
