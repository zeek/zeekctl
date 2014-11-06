# Tasks which are to be done on a regular basis from cron.

import os
import time
import shutil

import util
import config
import execute
import control
import plugin

# Triggers all activity which is to be done regularly via cron.
def doCron(watch):
    if not config.Config.cronenabled:
        return cmdout

    if not os.path.exists(os.path.join(config.Config.scriptsdir, "broctl-config.sh")):
        cmdout.error("broctl-config.sh not found (try 'broctl install')")
        return cmdout

    config.Config.config["cron"] = "1"  # Flag to indicate that we're running from cron.

    if not util.lock(cmdout):
        return cmdout

    util.bufferOutput()

    if watch:
        # Check whether nodes are still running and restart if necessary.
        for (node, isrunning) in control.isRunning(config.Config.nodes(), cmdout):
            if not isrunning and node.hasCrashed():
                results, cmdout_start = control.start([node])
                cmdout.append(cmdout_start)

    # Check for dead hosts.
    _checkHosts(cmdout)

    # Generate statistics.
    _logStats(5, cmdout)

    # Check available disk space.
    _checkDiskSpace(cmdout)

    # Expire old log files.
    _expireLogs(cmdout)

    # Update the HTTP stats directory.
    _updateHTTPStats(cmdout)

    # Run external command if we have one.
    if config.Config.croncmd:
        (success, output) = execute.runLocalCmd(config.Config.croncmd)
        if not success:
            cmdout.error("failure running croncmd: %s" % config.Config.croncmd)

    # Mail potential output.
    cmdout.printResults()
    output = util.getBufferedOutput()
    if output:
        if not util.sendMail("cron: " + output.split("\n")[0], output):
            cmdout.error("cannot send mail")

    util.unlock(cmdout)

    config.Config.config["cron"] = "0"
    util.debug(1, "cron done")

    return cmdout

def _logStats(interval, cmdout):

    nodes = config.Config.nodes()
    top = control.getTopOutput(nodes, cmdout)

    have_cflow = config.Config.cflowaddress and config.Config.cflowuser and config.Config.cflowpassword
    have_capstats = config.Config.capstatspath
    cflow_start = cflow_end = None
    capstats = []
    cflow_rates = []

    if have_cflow:
        cflow_start = control.getCFlowStatus(cmdout)

    if have_capstats:
        capstats = control.getCapstatsOutput(nodes, interval, cmdout)

    elif have_cflow:
        time.sleep(interval)

    if have_cflow:
        cflow_end = control.getCFlowStatus(cmdout)
        if cflow_start and cflow_end:
            cflow_rates = control.calculateCFlowRate(cflow_start, cflow_end, interval)

    t = time.time()

    out = open(config.Config.statslog, "a")

    for (node, error, vals) in top:
        if not error:
            for proc in vals:
                type = proc["proc"]
                for (val, key) in proc.items():
                    if val != "proc":
                        out.write("%s %s %s %s %s\n" % (t, node, type, val, key))
        else:
            out.write("%s %s error error %s\n" % (t, node, error))

    for (node, netif, error, vals) in capstats:
        if not error:
            for (key, val) in vals.items():
                out.write("%s %s interface %s %s\n" % (t, node, key, val))

                if key == "pkts" and str(node) != "$total":
                    # Report if we don't see packets on an interface.
                    tag = "lastpkts-%s" % node.name.lower()

                    if tag in config.Config.state:
                        last = float(config.Config.state[tag])
                    else:
                        last = -1.0

                    if float(val) == 0.0 and last != 0.0:
                        cmdout.info("%s is not seeing any packets on interface %s" % (node.host, netif))

                    if float(val) != 0.0 and last == 0.0:
                        cmdout.info("%s is seeing packets again on interface %s" % (node.host, netif))

                    config.Config._setState(tag, val)

        else:
            out.write("%s %s error error %s\n" % (t, node, error))

    for (port, error, vals) in cflow_rates:
        if not error:
            for (key, val) in vals.items():
                out.write("%s cflow %s %s %s\n" % (t, port.lower(), key, val))

    out.close()

def _checkDiskSpace(cmdout):

    minspace = float(config.Config.mindiskspace)
    if minspace == 0.0:
        return

    results = control.getDf(config.Config.hosts(), cmdout)
    for (nodehost, dfs) in results:
        host = nodehost.split("/")[1]

        for df in dfs:
            if df[0] == "FAIL":
                # A failure here is normally caused by a host that is down, so
                # we don't need to output the error message.
                continue

            fs = df[0]
            perc = df[4]
            key = ("disk-space-%s%s" % (host, fs.replace("/", "-"))).lower()

            if perc > 100 - minspace:
                if key in config.Config.state:
                    if float(config.Config.state[key]) > 100 - minspace:
                        # Already reported.
                        continue

                cmdout.warn("Disk space low on %s:%s - %.1f%% used." % (host, fs, perc))

            config.Config.state[key] = "%.1f" % perc

def _expireLogs(cmdout):

    i = int(config.Config.logexpireinterval)
    i2 = int(config.Config.statslogexpireinterval)

    if i == 0 and i2 == 0:
        return

    (success, output) = execute.runLocalCmd(os.path.join(config.Config.scriptsdir, "expire-logs"))

    if not success:
        cmdout.error("expire-logs failed\n\n")
        cmdout.error(output)

def _checkHosts(cmdout):

    for node in config.Config.hosts(nolocal=True):
        tag = "alive-%s" % node.host.lower()
        # TODO: fix
        #alive = execute.isAlive(node.addr, cmdout) and "1" or "0"

        if tag in config.Config.state:
            previous = config.Config.state[tag]

            if alive != previous:
                plugin.Registry.hostStatusChanged(node.host, alive == "1")
                cmdout.info("host %s %s" % (node.host, alive == "1" and "up" or "down"))

        config.Config._setState(tag, alive)


def _updateHTTPStats(cmdout):
    # Create meta file.
    if not os.path.exists(config.Config.statsdir):
        try:
            os.makedirs(config.Config.statsdir)
        except OSError as err:
            cmdout.error("failure creating directory: %s" % err)
            return

        cmdout.info("creating directory for stats file: %s" % config.Config.statsdir)

    metadat = os.path.join(config.Config.statsdir, "meta.dat")
    try:
        meta = open(metadat, "w")
    except IOError as err:
        cmdout.error("failure creating file: %s" % err)
        return

    for node in config.Config.hosts():
        meta.write("node %s %s %s\n" % (node, node.type, node.host))

    meta.write("time %s\n" % time.asctime())
    meta.write("version %s\n" % config.Config.version)

    try:
        meta.write("os %s\n" % execute.runLocalCmd("uname -a")[1][0])
    except IndexError:
        meta.write("os <error>\n")

    try:
        meta.write("host %s\n" % execute.runLocalCmd("hostname")[1][0])
    except IndexError:
        meta.write("host <error>\n")

    meta.close()

    wwwdir = os.path.join(config.Config.statsdir, "www")
    if not os.path.isdir(wwwdir):
        try:
            os.makedirs(wwwdir)
        except OSError as err:
            cmdout.error("failed to create directory: %s" % err)
            return

    # Append the current stats.log in spool to the one in ${statsdir}
    dst = os.path.join(config.Config.statsdir, os.path.basename(config.Config.statslog))
    try:
        fdst = open(dst, "a")
    except IOError as err:
        cmdout.error("failed to append to file: %s" % err)
        return

    fsrc = open(config.Config.statslog, "r")
    shutil.copyfileobj(fsrc, fdst)
    fdst.close()
    fsrc.close()

    # Update the WWW data
    statstocsv = os.path.join(config.Config.scriptsdir, "stats-to-csv")

    (success, output) = execute.runLocalCmd("%s %s %s %s" % (statstocsv, config.Config.statslog, metadat, wwwdir))
    if not success:
        cmdout.error("stats-to-csv failed")
        return

    os.unlink(config.Config.statslog)
    shutil.copy(metadat, wwwdir)

