# Functions to install files on all nodes.

import os
import re
import json

from BroControl import util
from BroControl import config
from BroControl import graph

# In all paths given in this file, ${<option>} will replaced with the value of
# the corresponding configuration option.

# Directories/files in form (path, mirror) which are synced from the manager to
# all nodes.
# If 'mirror' is true, the path is fully mirrored recursively, otherwise the
# directory is just created.
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
    ("${policydirsiteinstall}", True),
    ("${policydirsiteinstallauto}", True),
    ("${broctlconfigdir}/broctl-config.sh", True)
    ]

    return nfssyncs

# Generate shell script that sets Broctl dynamic variables according
# to their current values.  This shell script gets included in all
# other scripts.
def generateDynamicVariableScript(cmdout):
    cfg_path = os.path.join(config.Config.broctlconfigdir, "broctl-config.sh")
    cfg_file = open(cfg_path, 'w')
    for substvartuple in config.Config.options():
        substvar = substvartuple[0]
        # don't write out if it has an invalid bash variable name
        if not re.search("-", substvar):
            substvarvalue = substvartuple[1]
            cfg_file.write("%s=\"%s\"\n" % (substvar.replace(".", "_"), substvarvalue))
    cfg_file.close()

    symlink = os.path.join(config.Config.scriptsdir, "broctl-config.sh")

    try:
        if os.readlink(symlink) != cfg_path:
            # attempt to update the symlink
            try:
                util.force_symlink(cfg_path, symlink)
            except OSError as e:
                cmdout.error("failed to update symlink '%s' to point to '%s': %s" % (symlink, cfg_path, e.strerror))
                return False
    except OSError as e:
        cmdout.error("failed to resolve symlink '%s': %s" % (symlink, e.strerror))
        return False

    return True


# Create Bro-side broctl configuration broctl-layout.bro.
def makeLayout(path, cmdout, silent=False):
    class port:
        def __init__(self, startport):
            self.p = startport

        def nextPort(self, node):
            self.p += 1
            node.setPort(self.p)
            return self.p

    manager = config.Config.manager()

    if not manager:
        return

    broport = port(int(config.Config.broport) - 1)

    filename = os.path.join(path, "cluster-layout.bro")

    # If there is a standalone node, delete any cluster-layout file to
    # avoid the cluster framework from activating and get out of here.
    if config.Config.nodes("standalone"):
        if os.access(filename, os.W_OK):
            os.unlink(filename)
        # We do need to establish the port for the manager.
        if not silent:
            cmdout.info("generating standalone-layout.bro ...")

        filename = os.path.join(path, "standalone-layout.bro")
        out = open(filename, "w")
        out.write("# Automatically generated. Do not edit.\n")
        # This is the port that standalone nodes listen on for remote control by default.
        out.write("redef Communication::listen_port = %s/tcp;\n" % broport.nextPort(manager))
        out.write("redef Communication::nodes += {\n")
        out.write("	[\"control\"] = [$host=%s, $zone_id=\"%s\", $class=\"control\", $events=Control::controller_events],\n" % (util.formatBroAddr(manager.addr), manager.zone_id))
        out.write("};\n")
        out.close()

    else:
        if not silent:
            cmdout.info("generating cluster-layout.bro ...")

        out = open(filename, "w")

        workers = config.Config.nodes("workers")
        proxies = config.Config.nodes("proxies")

        out.write("# Automatically generated. Do not edit.\n")
        out.write("redef Cluster::nodes = {\n")

        # Control definition.  For now just reuse the manager information.
        out.write("\t[\"control\"] = [$node_type=Cluster::CONTROL, $ip=%s, $zone_id=\"%s\", $p=%s/tcp],\n" % (util.formatBroAddr(manager.addr), config.Config.zoneid, broport.nextPort(manager)))

        # Manager definition
        out.write("\t[\"%s\"] = [$node_type=Cluster::MANAGER, $ip=%s, $zone_id=\"%s\", $p=%s/tcp, $workers=set(" % (manager.name, util.formatBroAddr(manager.addr), manager.zone_id, broport.nextPort(manager)))
        for s in workers:
            out.write("\"%s\"" % s.name)
            if s != workers[-1]:
                out.write(", ")
        out.write(")],\n")

        # Proxies definition
        for p in proxies:
            out.write("\t[\"%s\"] = [$node_type=Cluster::PROXY, $ip=%s, $zone_id=\"%s\", $p=%s/tcp, $manager=\"%s\", $workers=set(" % (p.name, util.formatBroAddr(p.addr), p.zone_id, broport.nextPort(p), manager.name))
            for s in workers:
                out.write("\"%s\"" % s.name)
                if s != workers[-1]:
                    out.write(", ")
            out.write(")],\n")

        # Workers definition
        for w in workers:
            p = w.count % len(proxies)
            out.write("\t[\"%s\"] = [$node_type=Cluster::WORKER, $ip=%s, $zone_id=\"%s\", $p=%s/tcp, $interface=\"%s\", $manager=\"%s\", $proxy=\"%s\"],\n" % (w.name, util.formatBroAddr(w.addr), w.zone_id, broport.nextPort(w), w.interface, manager.name, proxies[p].name))

        # Activate time-machine support if configured.
        if config.Config.timemachinehost:
            out.write("\t[\"time-machine\"] = [$node_type=Cluster::TIME_MACHINE, $ip=%s, $p=%s],\n" % (config.Config.timemachinehost, config.Config.timemachineport))

        out.write("};\n")

        out.close()

# Reads in a list of networks from file.
def readNetworks(file):

    nets = []

    for line in open(file):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        fields = line.split(None, 1)

        cidr = util.formatBroPrefix(fields[0])
        tag = ""
        if len(fields) == 2:
            tag = fields[1]

        nets += [(cidr, tag)]

    return nets


# Create Bro script which contains a list of local networks.
def makeLocalNetworks(path, cmdout, silent=False):

    netcfg = config.Config.localnetscfg

    if not os.path.exists(netcfg):
        cmdout.error("list of local networks does not exist in %s" % netcfg)
        return False

    if not silent:
        cmdout.info("generating local-networks.bro ...")

    nets = readNetworks(netcfg)

    out = open(os.path.join(path, "local-networks.bro"), "w")
    out.write("# Automatically generated. Do not edit.\n\n")

    out.write("redef Site::local_nets = {\n")
    for (cidr, tag) in nets:
        out.write("\t%s," % cidr)
        if tag:
            out.write("\t# %s" % tag)
        out.write("\n")
    out.write("};\n\n")
    out.close()

    return True


def makeConfig(path, cmdout, silent=False):
    manager = config.Config.manager()

    if not manager:
        return

    if not silent:
        cmdout.info("generating broctl-config.bro ...")

    filename = os.path.join(path, "broctl-config.bro")
    out = open(filename, "w")
    out.write("# Automatically generated. Do not edit.\n")
    out.write("redef Notice::mail_dest = \"%s\";\n" % config.Config.mailto)
    out.write("redef Notice::mail_dest_pretty_printed = \"%s\";\n" % config.Config.mailalarmsto)
    out.write("redef Notice::sendmail  = \"%s\";\n" % config.Config.sendmail)
    out.write("redef Notice::mail_subject_prefix  = \"%s\";\n" % config.Config.mailsubjectprefix)
    out.write("redef Notice::mail_from  = \"%s\";\n" % config.Config.mailfrom)
    if manager.type != "standalone":
        out.write("@if ( Cluster::local_node_type() == Cluster::MANAGER )\n")
    out.write("redef Log::default_rotation_interval = %s secs;\n" % config.Config.logrotationinterval)
    out.write("redef Log::default_mail_alarms_interval = %s secs;\n" % config.Config.mailalarmsinterval)
    if manager.type != "standalone":
        out.write("@endif\n")
    if config.Config.ipv6comm == "1":
        out.write("redef Communication::listen_ipv6 = T ;\n")
    else:
        out.write("redef Communication::listen_ipv6 = F ;\n")

    out.close()

# Write individual node.cfg files per successor in the hierarchy
def makeNodeConfigs(path, nodes, cmdout, silent=False):
    overlay = config.Config.overlay
    head = config.Config.head()

    if not silent:
        cmdout.info("generating node.cfg per peer ...")

    for n in nodes:
        npath = path + "/node.cfg_" + str(n)
        g = overlay.getSubgraph(n)

        with open(npath, 'w') as f:
            f.write("{\n")
            # head entry
            f.write("head: {")
            f.write("\"id\": " + str(head.id) + ",")
            if hasattr(head, "cluster"):
                f.write("\"cluster\": " + str(head.cluster) + ",")
            if hasattr(head, "host"):
                f.write("\"host\": " + str(head.host) + ",")
            f.write("},\n")

            # node entries
            f.write("nodes: [\n")
            for n2 in g.nodes():
                entry = json.JSONEncoder().encode(overlay.node_attr["json-data"][n2])
                f.write(entry + ",\n")
            f.write("],\n")

            # connection entries
            f.write("connections: [\n")
            for (u, v) in g.edges():
                f.write("{\"from\": \"" + str(u) + "\", \"to\": \"" + str(v) + "\"},\n")
            f.write("],\n")

            f.write("}\n")
