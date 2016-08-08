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
    # Rather than just overwriting the file, we first write out a tmp file,
    # and then rename it to avoid a race condition where a process outside of
    # broctl (such as archive-log) is trying to read the file while it is
    # being written.
    cfg_path = os.path.join(config.Config.broctlconfigdir, "broctl-config.sh")
    tmp_path = os.path.join(config.Config.broctlconfigdir, ".broctl-config.sh.tmp")

    with open(tmp_path, "w") as out:
        for (varname, value) in config.Config.options(dynamic=False):
            if isinstance(value, bool):
                # Convert bools to the string "1" or "0"
                value = (value and "1" or "0")
            else:
                value = str(value)

            # In order to prevent shell errors, here we convert plugin
            # option names to use underscores, and double quotes in the value
            # are escaped.
            out.write('%s="%s"\n' % (varname.replace(".", "_"),
                       value.replace('"', '\\"')))

    os.rename(tmp_path, cfg_path)

    symlink = os.path.join(config.Config.scriptsdir, "broctl-config.sh")

    if not os.path.islink(symlink) or os.readlink(symlink) != cfg_path:
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
            self.p = startport

        def next_port(self, node):
            self.p += 1
            node.setPort(self.p)
            return self.p

    manager = config.Config.manager()

    if config.Config.nodes("standalone"):
        if not silent:
            cmdout.info("generating standalone-layout.bro ...")

        filename = os.path.join(path, "standalone-layout.bro")
        with open(filename, "w") as out:
            out.write("# Automatically generated. Do not edit.\n")
            # This is the port that standalone nodes listen on for remote
            # control by default.
            out.write("redef Communication::listen_port = %s/tcp;\n" % config.Config.broport)
            out.write("redef Communication::nodes += {\n")
            out.write("\t[\"control\"] = [$host=%s, $zone_id=\"%s\", $class=\"control\", $events=Control::controller_events],\n" % (util.format_bro_addr(manager.addr), manager.zone_id))
            out.write("};\n")

    else:
        if not silent:
            cmdout.info("generating cluster-layout.bro ...")

        filename = os.path.join(path, "cluster-layout.bro")
        broport = Port(config.Config.broport)
        workers = config.Config.nodes("workers")
        proxies = config.Config.nodes("proxies")
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
        ostr += '\t["control"] = [$node_type=Cluster::CONTROL, $ip=%s, $zone_id="%s", $p=%s/tcp],\n' % (util.format_bro_addr(manager.addr), config.Config.zoneid, config.Config.broport)

        # Logger definition
        if loggers:
            ostr += '\t["%s"] = [$node_type=Cluster::LOGGER, $ip=%s, $zone_id="%s", $p=%s/tcp],\n' % (logger.name, util.format_bro_addr(logger.addr), logger.zone_id, broport.next_port(logger))

        # Manager definition
        ostr += '\t["%s"] = [$node_type=Cluster::MANAGER, $ip=%s, $zone_id="%s", $p=%s/tcp, %s$workers=set(' % (manager.name, util.format_bro_addr(manager.addr), manager.zone_id, broport.next_port(manager), loggerstr)
        for s in workers:
            ostr += '"%s"' % s.name
            if s != workers[-1]:
                ostr += ", "
        ostr += ")],\n"

        # Proxies definition
        for p in proxies:
            ostr += '\t["%s"] = [$node_type=Cluster::PROXY, $ip=%s, $zone_id="%s", $p=%s/tcp, %s$manager="%s", $workers=set(' % (p.name, util.format_bro_addr(p.addr), p.zone_id, broport.next_port(p), loggerstr, manager.name)
            for s in workers:
                ostr += '"%s"' % s.name
                if s != workers[-1]:
                    ostr += ", "
            ostr += ")],\n"

        # Workers definition
        for w in workers:
            p = w.count % len(proxies)
            ostr += '\t["%s"] = [$node_type=Cluster::WORKER, $ip=%s, $zone_id="%s", $p=%s/tcp, $interface="%s", %s$manager="%s", $proxy="%s"],\n' % (w.name, util.format_bro_addr(w.addr), w.zone_id, broport.next_port(w), w.interface, loggerstr, manager.name, proxies[p].name)

        # Activate time-machine support if configured.
        if config.Config.timemachinehost:
            ostr += '\t["time-machine"] = [$node_type=Cluster::TIME_MACHINE, $ip=%s, $p=%s],\n' % (config.Config.timemachinehost, config.Config.timemachineport)

        ostr += "};\n"

        with open(filename, "w") as out:
            out.write(ostr)


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

    if not os.path.exists(netcfg):
        cmdout.error("file not found: %s" % netcfg)
        return False

    nets = read_networks(netcfg)

    with open(os.path.join(path, "local-networks.bro"), "w") as out:
        out.write("# Automatically generated. Do not edit.\n\n")

        out.write("redef Site::local_nets = {\n")
        for (cidr, tag) in nets:
            out.write("\t%s," % cidr)
            if tag:
                out.write("\t# %s" % tag)
            out.write("\n")
        out.write("};\n\n")

    return True


def make_broctl_config_policy(path, cmdout, plugin_reg, silent=False):
    manager = config.Config.manager()

    filename = os.path.join(path, "broctl-config.bro")
    with open(filename, "w") as out:
        out.write("# Automatically generated. Do not edit.\n")
        out.write("redef Notice::mail_dest = \"%s\";\n" % config.Config.mailto)
        out.write("redef Notice::mail_dest_pretty_printed = \"%s\";\n" % config.Config.mailalarmsto)
        out.write("redef Notice::sendmail  = \"%s\";\n" % config.Config.sendmail)
        out.write("redef Notice::mail_subject_prefix  = \"%s\";\n" % config.Config.mailsubjectprefix)
        out.write("redef Notice::mail_from  = \"%s\";\n" % config.Config.mailfrom)
        if manager.type != "standalone":
            loggers = config.Config.nodes("loggers")
            if loggers:
                ntype = "LOGGER"
            else:
                ntype = "MANAGER"
            out.write("@if ( Cluster::local_node_type() == Cluster::%s )\n" % ntype)
        out.write("redef Log::default_rotation_interval = %s secs;\n" % config.Config.logrotationinterval)
        out.write("redef Log::default_mail_alarms_interval = %s secs;\n" % config.Config.mailalarmsinterval)

        if manager.type != "standalone":
            out.write("@endif\n")

        if config.Config.ipv6comm:
            out.write("redef Communication::listen_ipv6 = T ;\n")
        else:
            out.write("redef Communication::listen_ipv6 = F ;\n")

        out.write("redef Pcap::snaplen = %s;\n" % config.Config.pcapsnaplen)
        out.write("redef Pcap::bufsize = %s;\n" % config.Config.pcapbufsize)

        out.write(plugin_reg.getBroctlConfig())
