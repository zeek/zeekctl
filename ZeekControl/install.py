# Functions to install files on all nodes.

import binascii
import os

from ZeekControl import config, util

# In all paths given in this file, ${<option>} will replaced with the value of
# the corresponding configuration option.


# Directories/files in form (path, mirror, optional) which are synced from the manager to
# all remote hosts.
# If "mirror" is False, then the path is assumed to be a directory and it will
# just be created on the remote host.  If "mirror" is True, then the path
# is fully mirrored recursively.  If "optional" is True, then it's ok for
# the path to not exist on the manager.
def get_syncs():
    syncs = [
        ("${zeekbase}", False, False),
        ("${zeekbase}/share", True, False),
        ("${cfgdir}", True, False),
        ("${libdir}", True, True),
        ("${libdir64}", True, True),
        ("${bindir}", True, False),
        ("${policydirsiteinstall}", True, False),
        ("${policydirsiteinstallauto}", True, False),
        # ("${policydir}", True, False),
        # ("${staticdir}", True, False),
        ("${logdir}", False, False),
        ("${spooldir}", False, False),
        ("${fileextractdir}", False, False),
        ("${tmpdir}", False, False),
        ("${zeekctlconfigdir}/zeekctl-config.sh", True, False),
    ]

    return syncs


# In NFS-mode, only these will be synced.
def get_nfssyncs():
    nfssyncs = [
        ("${spooldir}", False, False),
        ("${fileextractdir}", False, False),
        ("${tmpdir}", False, False),
        ("${policydirsiteinstall}", True, False),
        ("${policydirsiteinstallauto}", True, False),
        ("${zeekctlconfigdir}/zeekctl-config.sh", True, False),
    ]

    return nfssyncs


# Determine relative cfg_path
def splitall(path):
    """Break out all parts of a path into a list"""
    allparts = []
    while True:
        parts = os.path.split(path)
        if parts[0] == path:
            allparts.insert(0, parts[0])
            break
        if parts[1] == path:
            allparts.insert(0, parts[1])
            break
        path = parts[0]
        allparts.insert(0, parts[1])
    return allparts


def relpath(src, dst):
    """Calculate the relative path to dst)"""
    srcparts = splitall(src)
    dstparts = splitall(dst)
    while srcparts and dstparts and srcparts[0] == dstparts[0]:
        srcparts.pop(0)
        dstparts.pop(0)
    relparts = (len(dstparts) - 1) * [".."] + srcparts
    return os.path.join(*relparts)


# Generate a shell script "zeekctl-config.sh" that sets env. vars. that
# correspond to zeekctl config options.
def make_zeekctl_config_sh(cmdout):
    ostr = ""
    for varname, value in config.Config.options(dynamic=False):
        if isinstance(value, bool):
            # Convert bools to the string "1" or "0"
            value = "1" if value else "0"
        else:
            value = str(value)

        # In order to prevent shell errors, here we convert plugin
        # option names to use underscores, and double quotes in the value
        # are escaped.
        ostr += '{}="{}"\n'.format(varname.replace(".", "_"), value.replace('"', '\\"'))

    # Rather than just overwriting the file, we first write out a tmp file,
    # and then rename it to avoid a race condition where a process outside of
    # zeekctl (such as archive-log) is trying to read the file while it is
    # being written.
    cfg_path = os.path.join(config.Config.zeekctlconfigdir, "zeekctl-config.sh")
    tmp_path = os.path.join(config.Config.zeekctlconfigdir, ".zeekctl-config.sh.tmp")

    try:
        with open(tmp_path, "w") as out:
            out.write(ostr)
    except OSError as e:
        cmdout.error(f"failed to write file: {e}")
        return False

    try:
        os.rename(tmp_path, cfg_path)
    except OSError as e:
        cmdout.error(f"failed to rename file {tmp_path}: {e}")
        return False

    symlink = os.path.join(config.Config.scriptsdir, "zeekctl-config.sh")

    # Use a relative path instead of absolute (at request/usage of the FreeBSD
    # port, see https://github.com/zeek/zeekctl/pull/22)
    sym_cfg_path = relpath(cfg_path, symlink)

    # check if the symlink needs to be updated
    try:
        update_link = (
            not os.path.islink(symlink) or os.readlink(symlink) != sym_cfg_path
        )
    except OSError as e:
        cmdout.error(f"failed to read symlink: {e}")
        return False

    if update_link:
        # attempt to update the symlink
        try:
            util.force_symlink(sym_cfg_path, symlink)
        except OSError as e:
            cmdout.error(
                f"failed to update symlink '{symlink}' to point to '{sym_cfg_path}': {e.strerror}"
            )
            return False

    return True


# Create Zeek-side zeekctl configuration file.
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
    zeekport = Port(config.Config.zeekport)
    metricsport = None
    if config.Config.metricsport != 0:
        metricsport = Port(config.Config.metricsport)

    if config.Config.standalone:
        if not silent:
            cmdout.info("generating standalone-layout.zeek ...")

        filename = os.path.join(path, "standalone-layout.zeek")

        ostr = "# Automatically generated. Do not edit.\n"
        # This is the port that standalone nodes listen on for remote
        # control by default.
        ostr += f"redef Broker::default_port = {zeekport.use_port(manager)}/tcp;\n"
        ostr += '@if ( getenv("ZEEKCTL_DISABLE_LISTEN") == "" )\n'
        ostr += f"redef Telemetry::metrics_port = {metricsport.use_port(None)}/tcp;\n"
        ostr += "@endif\n"
        ostr += "\n"
        ostr += "event zeek_init()\n"
        ostr += "\t{\n"
        ostr += '\tif ( getenv("ZEEKCTL_DISABLE_LISTEN") == "" )\n'
        ostr += "\t\tBroker::listen();\n"
        ostr += "\t}\n"

    else:
        if not silent:
            cmdout.info("generating cluster-layout.zeek ...")

        filename = os.path.join(path, "cluster-layout.zeek")
        workers = config.Config.workers()
        proxies = config.Config.proxies()
        loggers = config.Config.loggers()

        # If no loggers are defined, then manager does the logging.
        manager_is_logger = "F" if loggers else "T"

        ostr = "# Automatically generated. Do not edit.\n"
        ostr += f"redef Cluster::manager_is_logger = {manager_is_logger};\n"
        ostr += "redef Cluster::nodes = {\n"

        # Control definition.  For now just reuse the manager information.
        ostr += f'\t["control"] = [$node_type=Cluster::CONTROL, $ip={util.format_zeek_addr(manager.addr)}, $p={zeekport.use_port(None)}/tcp],\n'

        # Manager definition. Manager should come first so that the metrics port
        # set in zeekctl.cfg will be the one used for the manager.
        ostr += f'\t["{manager.name}"] = [$node_type=Cluster::MANAGER, $ip={util.format_zeek_addr(manager.addr)}, $p={zeekport.use_port(manager)}/tcp'
        if metricsport:
            ostr += f", $metrics_port={metricsport.use_port(None)}/tcp"
        ostr += "],\n"

        # Loggers definition
        for lognode in loggers:
            ostr += f'\t["{lognode.name}"] = [$node_type=Cluster::LOGGER, $ip={util.format_zeek_addr(lognode.addr)}, $p={zeekport.use_port(lognode)}/tcp'
            if metricsport:
                ostr += f", $metrics_port={metricsport.use_port(None)}/tcp"
            ostr += "],\n"

        # Proxies definition (all proxies use same logger as the manager)
        for p in proxies:
            ostr += f'\t["{p.name}"] = [$node_type=Cluster::PROXY, $ip={util.format_zeek_addr(p.addr)}, $p={zeekport.use_port(p)}/tcp, $manager="{manager.name}"'
            if metricsport:
                ostr += f", $metrics_port={metricsport.use_port(None)}/tcp"
            ostr += "],\n"

        # Workers definition
        for w in workers:
            p = w.count % len(proxies)
            ostr += f'\t["{w.name}"] = [$node_type=Cluster::WORKER, $ip={util.format_zeek_addr(w.addr)}, $p={zeekport.use_port(w)}/tcp, $manager="{manager.name}"'
            if metricsport:
                ostr += f", $metrics_port={metricsport.use_port(None)}/tcp"
            ostr += "],\n"

        # Activate time-machine support if configured.
        if config.Config.timemachinehost:
            ostr += f'\t["time-machine"] = [$node_type=Cluster::TIME_MACHINE, $ip={config.Config.timemachinehost}, $p={config.Config.timemachineport}],\n'

        ostr += "};\n"

    # If UseWebSocket is True, render a zeek_init() handler that starts a WebSocket
    # server on the manager node.
    if config.Config.usewebsocket:
        ostr += "\n"
        ostr += "event zeek_init()\n\t{\n"
        ostr += '\tif ( getenv("ZEEKCTL_DISABLE_LISTEN") == "" && (Cluster::local_node_type() == Cluster::MANAGER || ! Cluster::is_enabled()) )\n'
        ostr += "\t\t{\n"
        ostr += f"\t\tCluster::listen_websocket([$listen_addr={config.Config.websockethost}, $listen_port={config.Config.websocketport}/tcp]);\n"
        ostr += "\t\t}\n"
        ostr += "\t}\n"

    try:
        with open(filename, "w") as out:
            out.write(ostr)
    except OSError as e:
        cmdout.error(f"failed to write file: {e}")
        return False

    return True


# Reads in a list of networks from file.
def read_networks(fname):
    nets = []

    with open(fname) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            fields = line.split(None, 1)

            cidr = util.format_zeek_prefix(fields[0])
            tag = fields[1] if len(fields) == 2 else ""

            nets += [(cidr, tag)]

    return nets


# Create Zeek script which contains a list of local networks.
def make_local_networks(path, cmdout):
    netcfg = config.Config.localnetscfg

    try:
        nets = read_networks(netcfg)
    except IndexError:
        cmdout.error(f"invalid CIDR notation in file: {netcfg}")
        return False
    except OSError as e:
        cmdout.error(f"failed to read file: {e}")
        return False

    ostr = "# Automatically generated. Do not edit.\n\n"

    ostr += "redef Site::local_nets = {\n"
    for cidr, tag in nets:
        ostr += f"\t{cidr},"
        if tag:
            ostr += f"\t# {tag}"
        ostr += "\n"
    ostr += "};\n\n"

    try:
        with open(os.path.join(path, "local-networks.zeek"), "w") as out:
            out.write(ostr)
    except OSError as e:
        cmdout.error(f"failed to write file: {e}")
        return False

    return True


def make_zeekctl_config_policy(path, cmdout, plugin_reg):
    ostr = "# Automatically generated. Do not edit.\n"
    ostr += f'redef Notice::mail_dest = "{config.Config.mailto}";\n'
    ostr += (
        f'redef Notice::mail_dest_pretty_printed = "{config.Config.mailalarmsto}";\n'
    )
    ostr += f'redef Notice::sendmail = "{config.Config.sendmail}";\n'
    ostr += (
        f'redef Notice::mail_subject_prefix = "{config.Config.mailsubjectprefix}";\n'
    )
    ostr += f'redef Notice::mail_from = "{config.Config.mailfrom}";\n'
    ostr += f'redef Broker::table_store_db_directory = "{config.Config.brokerdbdir}";\n'
    if not config.Config.standalone:
        loggers = config.Config.loggers()
        ntype = "LOGGER" if loggers else "MANAGER"
        ostr += f"@if ( Cluster::local_node_type() == Cluster::{ntype} )\n"

    ostr += f"redef Log::default_rotation_interval = {config.Config.logrotationinterval} secs;\n"
    ostr += f"redef Log::default_mail_alarms_interval = {config.Config.mailalarmsinterval} secs;\n"

    if not config.Config.standalone:
        ostr += "@endif\n"

    ostr += f"redef Pcap::snaplen = {config.Config.pcapsnaplen};\n"
    ostr += f"redef Pcap::bufsize = {config.Config.pcapbufsize};\n"

    if not config.Config.privateaddressspaceislocal:
        ostr += "redef Site::private_address_space_is_local = F;\n"

    seed_str = make_global_hash_seed()
    ostr += f'redef global_hash_seed = "{seed_str}";\n'

    ostr += f'redef Cluster::default_store_dir = "{config.Config.defaultstoredir}";\n'

    if config.Config.compresslogsinflight > 0:
        ostr += f"redef LogAscii::gzip_level = {config.Config.compresslogsinflight};\n"
        ostr += f'redef LogAscii::gzip_file_extension = "{config.Config.compressextension}";\n'

    if config.Config.fileextractdir:
        ostr += f'redef FileExtract::prefix = "{config.Config.fileextractdir}/" + Cluster::node;\n'

    ostr += plugin_reg.getZeekctlConfig(cmdout)

    filename = os.path.join(path, "zeekctl-config.zeek")
    try:
        with open(filename, "w") as out:
            out.write(ostr)
    except OSError as e:
        cmdout.error(f"failed to write file: {e}")
        return False

    return True


# Create a new random seed value if one is not found in the state database (this
# ensures a consistent value after a restart).  Return a string representation.
def make_global_hash_seed():
    seed_str = config.Config.get_state("global-hash-seed")

    if not seed_str:
        # Get 4 bytes of random data (Zeek uses 4 bytes to create an initial
        # seed in the Hasher::MakeSeed() function if the Zeek script constant
        # global_hash_seed is an empty string).
        seed = os.urandom(4)

        # Convert each byte of seed value to a two-digit hex string.
        seed_str = binascii.hexlify(seed)
        seed_str = seed_str.decode()

        config.Config.set_state("global-hash-seed", seed_str)

    return seed_str
