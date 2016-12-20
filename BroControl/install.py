# Functions to install files on all nodes.

import os

from BroControl import util
from BroControl import config

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
            value = (value and "1" or "0")
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
        ostr += "redef Broker::listen_port = %s/tcp;\n" % broport.use_port(manager)
        ostr += "redef Broker::nodes += {\n"
        ostr += "\t[\"control\"] = [$ip=%s, $zone_id=\"%s\"],\n" % (util.format_bro_addr(manager.addr), manager.zone_id)
        ostr += "};\n"

    else:
        if not silent:
            cmdout.info("generating cluster-layout.bro ...")

        filename = os.path.join(path, "cluster-layout.bro")
        workers = config.Config.nodes("workers")
        datanodes = config.Config.nodes("datanodes")
        loggers = config.Config.nodes("loggers")

        if loggers:
            # Use the first logger in list, since only one logger is allowed.
            logger = loggers[0]
            manager_is_logger = "F"
            loggerstr = '$logger="%s", ' % logger.name
        else:
            # If no logger exists, then manager does the logging.
            manager_is_logger = "T"
            loggerstr = ""

        ostr = "# Automatically generated. Do not edit.\n"
        ostr += "redef Cluster::manager_is_logger = %s;\n" % manager_is_logger
        ostr += "redef Cluster::nodes = {\n"

        # Control definition.  For now just reuse the manager information.
        ostr += '\t["control"] = [$node_roles=set(Cluster::CONTROL), $ip=%s, $zone_id="%s", $p=%s/tcp],\n' % (util.format_bro_addr(manager.addr), config.Config.zoneid, broport.use_port(None))

        # Logger definition
        if loggers:
            ostr += '\t["%s"] = [$node_roles=set(Cluster::LOGGER), $ip=%s, $zone_id="%s", $p=%s/tcp],\n' % (logger.name, util.format_bro_addr(logger.addr), logger.zone_id, broport.use_port(logger))

        # Manager definition
        managerroles = "Cluster::MANAGER"
        if manager_is_logger == "T":
            managerroles += ", Cluster::LOGGER"
        ostr += '\t["%s"] = [$node_roles=set(%s), $ip=%s, $zone_id="%s", $p=%s/tcp, %s$workers=set(' % (manager.name, managerroles, util.format_bro_addr(manager.addr), manager.zone_id, broport.use_port(manager), loggerstr)
        for s in workers:
            ostr += '"%s"' % s.name
            if s != workers[-1]:
                ostr += ", "
        ostr += ")],\n"

        # Datanode definition
        for p in datanodes:
            ostr += '\t["%s"] = [$node_roles=set(Cluster::DATANODE), $ip=%s, $zone_id="%s", $p=%s/tcp, %s$manager="%s", $workers=set(' % (p.name, util.format_bro_addr(p.addr), p.zone_id, broport.use_port(p), loggerstr, manager.name)
            for s in workers:
                ostr += '"%s"' % s.name
                if s != workers[-1]:
                    ostr += ", "
            ostr += ")],\n"

        # Workers definition
        for w in workers:
            ostr += '\t["%s"] = [$node_roles=set(Cluster::WORKER), $ip=%s, $zone_id="%s", $p=%s/tcp, $interface="%s", %s$manager="%s", $datanode="%s"],\n' % (w.name, util.format_bro_addr(w.addr), w.zone_id, broport.use_port(w), w.interface, loggerstr, manager.name, datanodes[0].name)

        # Activate time-machine support if configured.
        if config.Config.timemachinehost:
            ostr += '\t["time-machine"] = [$node_roles=set(Cluster::TIME_MACHINE), $ip=%s, $p=%s],\n' % (config.Config.timemachinehost, config.Config.timemachineport)

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
            tag = ""
            if len(fields) == 2:
                tag = fields[1]

            nets += [(cidr, tag)]

    return nets


# Create Bro script which contains a list of local networks.
def make_local_networks(path, cmdout, silent=False):

    netcfg = config.Config.localnetscfg

    try:
        nets = read_networks(netcfg)
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


def make_broctl_config_policy(path, cmdout, plugin_reg, silent=False):
    manager = config.Config.manager()

    ostr = '# Automatically generated. Do not edit.\n'
    ostr += 'redef Notice::mail_dest = "%s";\n' % config.Config.mailto
    ostr += 'redef Notice::mail_dest_pretty_printed = "%s";\n' % config.Config.mailalarmsto
    ostr += 'redef Notice::sendmail = "%s";\n' % config.Config.sendmail
    ostr += 'redef Notice::mail_subject_prefix = "%s";\n' % config.Config.mailsubjectprefix
    ostr += 'redef Notice::mail_from = "%s";\n' % config.Config.mailfrom
    if manager.type != "standalone":
        loggers = config.Config.nodes("loggers")
        if loggers:
            ntype = "LOGGER"
        else:
            ntype = "MANAGER"
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

    ostr += plugin_reg.getBroctlConfig()

    filename = os.path.join(path, "broctl-config.bro")
    try:
        with open(filename, "w") as out:
            out.write(ostr)
    except IOError as e:
        cmdout.error("failed to write file: %s" % e)
        return False

    return True
