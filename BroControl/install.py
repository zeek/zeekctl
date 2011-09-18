# Functions to install files on all nodes. 

import os
import sys
import glob
import fileinput
import re

import util
import execute
import config

# In all paths given in this file, ${<option>} will replaced with the value of the
# corresponding configuration option.

# Diretories/files in form (path, mirror) which are synced from the manager to all nodes.
# If 'mirror' is true, the path is fully mirrored recursively, otherwise the
# directory is just created.
Syncs = [
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

# In NFS-mode, only these will be synced.
NFSSyncs = [
    ("${policydirsiteinstall}", True),
    ("${policydirsiteinstallauto}", True),
    ("${broctlconfigdir}/broctl-config.sh", True)
    ]

# Generate shell script that sets Broctl dynamic variables according
# to their current values.  This shell script gets included in all
# other scripts.
def generateDynamicVariableScript():
    cfg_path = os.path.join(config.Config.broctlconfigdir, "broctl-config.sh")
    cfg_file = open(cfg_path, 'w')
    for substvartuple in config.Config.options():
        substvar = substvartuple[0]
        # don't write out if it has an invalid bash variable name
        if not re.search("-", substvar):
            substvarvalue = substvartuple[1]
            cfg_file.write("%s=\"%s\"\n" % (substvar.replace(".", "_"), substvarvalue))
    cfg_file.close()

# Performs the complete broctl installion process.
#
# If local_only is True, nothing is propagated to other nodes.
def install(local_only):

    config.Config.determineBroVersion()

    manager = config.Config.manager()

    # Delete previously installed policy files to not mix things up.
    policies = [config.Config.policydirsiteinstall, config.Config.policydirsiteinstallauto]

    for p in policies:
        if os.path.isdir(p):
            util.output("removing old policies in %s ..." % p, False)
            execute.rmdir(manager, p)
            util.output(" done.")

    util.output("creating policy directories ...", False)
    for p in policies:
        execute.mkdir(manager, p)
    util.output(" done.")

    # Install local site policy.

    if config.Config.sitepolicypath:
        util.output("installing site policies ...", False)
        dst = config.Config.policydirsiteinstall
        for dir in config.Config.sitepolicypath.split(":"):
            dir = config.Config.subst(dir)
            for file in glob.glob(os.path.join(dir, "*")):
                if execute.isfile(manager, file):
                    execute.install(manager, file, dst)
        util.output(" done.")

    makeLayout()
    makeLocalNetworks()
    makeConfig()

    current = config.Config.subst(os.path.join(config.Config.logdir, "current"))
    if not execute.exists(manager, current):
        try:
            os.symlink(manager.cwd(), current)
        except (IOError, OSError), e:
            pass

    generateDynamicVariableScript()

    if local_only:
        return

    # Sync to clients.
    util.output("updating nodes ... ", False)

    hosts = {}
    nodes = []

    for n in config.Config.nodes():
        # Make sure we do each host only once.
        if n.host in hosts:
            continue

        hosts[n.host] = 1

        if n == manager:
            continue

        if not execute.isAlive(n.addr):
            continue

        nodes += [n]

    if config.Config.havenfs != "1":
        # Non-NFS, need to explicitly synchronize.
        dirs = []
        for dir in [config.Config.subst(dir) for (dir, mirror) in Syncs if not mirror]:
            dirs += [(n, dir) for n in nodes]

        for (node, success) in execute.mkdirs(dirs):
            if not success:
                util.warn("cannot create directory %s on %s" % (dir, node.name))

        paths = [config.Config.subst(dir) for (dir, mirror) in Syncs if mirror]
        execute.sync(nodes, paths)
        util.output("done.")

        # Note: the old code created $brobase explicitly but it seems the loop above should
        # already take care of that.

    else:
        # NFS. We only need to take care of the spool/log directories.
        paths = [config.Config.spooldir]
        paths += [config.Config.tmpdir]

        dirs = []
        for dir in paths:
            dirs += [(n, dir) for n in nodes]

        for dir in [config.Config.subst(dir) for (dir, mirror) in NFSSyncs if not mirror]:
            dirs += [(n, dir) for n in nodes]

        # We need this only on the manager.
        dirs += [(manager, config.Config.logdir)]

        for (node, success) in execute.mkdirs(dirs):
            if not success:
                util.warn("cannot create (some of the) directories %s on %s" % (",".join(paths), node.name))

        paths = [config.Config.subst(dir) for (dir, mirror) in NFSSyncs if mirror]
        execute.sync(nodes, paths)
        util.output("done.")

# Create Bro-side broctl configuration broctl-layout.bro.
port = -1
def makeLayout():
    def nextPort(node):
        global port
        port += 1
        node.setPort(port)
        return port

    global port
    port = 47759
    manager = config.Config.manager()

    if not manager:
        return

    filename = os.path.join(config.Config.policydirsiteinstallauto, "cluster-layout.bro")

    # If there is a standalone node, delete any cluster-layout file to
    # avoid the cluster framework from activating and get out of here.
    if ( len(config.Config.nodes("standalone")) > 0 ):
        if os.access(filename, os.W_OK):
            os.unlink(filename)
        # We do need to establish the port for the manager.
        util.output("generating standalone-layout.bro ...", False)

        filename = os.path.join(config.Config.policydirsiteinstallauto, "standalone-layout.bro")
        out = open(filename, "w")
        print >>out, "# Automatically generated. Do not edit."
        # This is the port that standalone nodes listen on for remote control by default.
        print >>out, "redef Communication::listen_port_clear = %s/tcp;" % nextPort(manager)

    else:
        util.output("generating cluster-layout.bro ...", False)

        out = open(filename, "w")

        workers = config.Config.nodes("workers")
        proxies = config.Config.nodes("proxies")

        print >>out, "# Automatically generated. Do not edit."
        print >>out, "redef Cluster::nodes = {";

        # Control definition.  For now just reuse the manager information.
        print >>out, "\t[\"control\"] = [$node_type=Cluster::CONTROL, $ip=%s, $p=%s/tcp]," % (manager.addr, nextPort(manager))

        # Manager definition
        print >>out, "\t[\"%s\"] = [$node_type=Cluster::MANAGER, $ip=%s, $p=%s/tcp, $workers=set(" % (manager.name, manager.addr, nextPort(manager)),
        for s in workers:
            print >>out, "\"%s\"" % (s.name),
            if s != workers[-1]:
                print >>out, ",",
        print >>out, ")],"

        # Proxies definition
        for p in proxies:
            print >>out, "\t[\"%s\"] = [$node_type=Cluster::PROXY, $ip=%s, $p=%s/tcp, $manager=\"%s\", $workers=set(" % (p.name, p.addr, nextPort(p), manager.name),
            for s in workers:
                print >>out, "\"%s\"" % (s.name),
                if s != workers[-1]:
                    print >>out, ",",
            print >>out, ")],"

        # Workers definition
        for w in workers:
            p = w.count % len(proxies)
            print >>out, "\t[\"%s\"] = [$node_type=Cluster::WORKER, $ip=%s, $p=%s/tcp, $interface=\"%s\", $manager=\"%s\", $proxy=\"%s\"]," % (w.name, w.addr, nextPort(w), w.interface, manager.name, proxies[p].name),

        # Activate time-machine support if configured.
        if config.Config.timemachinehost:
            print >>out, "[\"time-machine\"] = [$node_type=Cluster::TIME_MACHINE, $ip=%s, $p=%s/tcp]," % (config.Config.timemachinehost, config.Config.timemachineport),

        print >>out, "};"

        # TODO: This is definitely the wrong spot for this.
        #
        # This doesn't work at all right now ... -Robin
        #print >>out, "redef Cluster::log_dir = \"%s\";" % config.Config.subst(config.Config.logdir)

    util.output(" done.")

# Reads in a list of networks from file.
def readNetworks(file):

    nets = []

    for line in open(file):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        fields = line.split()
        nets += [(fields[0], " ".join(fields[1:]))]

    return nets


# Create Bro script which contains a list of local networks.
def makeLocalNetworks():

    netcfg = config.Config.localnetscfg

    if not os.path.exists(netcfg):
        util.warn("list of local networks does not exist in %s" % netcfg)
        return

    util.output("generating local-networks.bro ...", False)

    out = open(os.path.join(config.Config.policydirsiteinstallauto, "local-networks.bro"), "w")
    print >>out, "# Automatically generated. Do not edit.\n"

    netcfg = config.Config.localnetscfg

    if os.path.exists(netcfg):
        nets = readNetworks(netcfg)

        print >>out, "redef Site::local_nets = {"
        for (cidr, tag) in nets:
            print >>out, "\t%s," % cidr,
            if tag != "":
                print >>out, "\t# %s" % tag,
            print >>out
        print >>out, "};\n"

    util.output(" done.")


def makeConfig():
    manager = config.Config.manager()

    if not manager:
        return

    util.output("generating broctl-config.bro ...", False)
    filename = os.path.join(config.Config.policydirsiteinstallauto, "broctl-config.bro")
    out = open(filename, "w")
    print >>out, "# Automatically generated. Do not edit."
    print >>out, "redef Notice::mail_dest = \"%s\";" % config.Config.mailto
    print >>out, "redef Notice::sendmail  = \"%s\";" % config.Config.sendmail;
    print >>out, "redef Notice::mail_subject_prefix  = \"%s\";" % config.Config.mailsubjectprefix;
    out.close()
    util.output(" done.")


