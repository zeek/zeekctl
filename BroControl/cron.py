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

    if config.Config.cronenabled == "0":
        return

    if not os.path.exists(os.path.join(config.Config.scriptsdir, "broctl-config.sh")):
        util.output("error: broctl-config.sh not found (try 'broctl install')") 
        return

    config.Config.config["cron"] = "1"  # Flag to indicate that we're running from cron.

    if not util.lock():
        return

    util.bufferOutput()

    if watch:
        # Check whether nodes are still running an restart if neccessary.
        for (node, isrunning) in control.isRunning(config.Config.nodes()):
            if not isrunning and node.hasCrashed():
                control.start([node])

    # Check for dead hosts.
    _checkHosts()

    # Generate statistics.
    _logStats(5)

    # Check available disk space.
    _checkDiskSpace()

    # Expire old log files.
    _expireLogs()

    # Update the HTTP stats directory.
    _updateHTTPStats()

    # Run external command if we have one.
    if config.Config.croncmd:
        (success, output) = execute.runLocalCmd(config.Config.croncmd)
        if not success:
            util.output("error running croncmd: %s" % config.Config.croncmd)

    # Mail potential output.
    output = util.getBufferedOutput()
    if output:
        util.sendMail("cron: " + output.split("\n")[0], output)

    util.unlock()

    config.Config.config["cron"] = "0"
    util.debug(1, "cron done")

def logAction(node, action):
    t = time.time()
    out = open(config.Config.statslog, "a")
    print >>out, t, node, "action", action
    out.close()

def _logStats(interval):

    nodes = config.Config.nodes()
    top = control.getTopOutput(nodes)

    have_cflow = config.Config.cflowaddress and config.Config.cflowuser and config.Config.cflowpassword
    have_capstats = config.Config.capstatspath
    cflow_start = cflow_end = None
    capstats = []
    cflow_rates = []

    if have_cflow:
        cflow_start = control.getCFlowStatus()

    if have_capstats:
        capstats = control.getCapstatsOutput(nodes, interval)

    elif have_cflow:
        time.sleep(interval)

    if have_cflow:
        cflow_end = control.getCFlowStatus()
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
                        print >>out, t, node, type, val, key
        else:
            print >>out, t, node, "error", "error", error

    for (node, netif, error, vals) in capstats:
        if not error:
            for (key, val) in vals.items():
                print >>out, t, node, "interface", key, val

                if key == "pkts" and str(node) != "$total":
                    # Report if we don't see packets on an interface.
                    tag = "lastpkts-%s" % node.name.lower()

                    if tag in config.Config.state:
                        last = float(config.Config.state[tag])
                    else:
                        last = -1.0

                    if float(val) == 0.0 and last != 0.0:
                        util.output("%s is not seeing any packets on interface %s" % (node.host, netif))

                    if float(val) != 0.0 and last == 0.0:
                        util.output("%s is seeing packets again on interface %s" % (node.host, netif))

                    config.Config._setState(tag, val)

        else:
            print >>out, t, node, "error", "error", error

    for (port, error, vals) in cflow_rates:
        if not error:
            for (key, val) in vals.items():
                print >>out, t, "cflow", port.lower(), key, val

    out.close()

def _checkDiskSpace():

    minspace = float(config.Config.mindiskspace)
    if minspace == 0.0:
        return

    results = control.getDf(config.Config.hosts())
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

                util.output("Disk space low on %s:%s - %.1f%% used." % (host, fs, perc))

            config.Config.state[key] = "%.1f" % perc

def _expireLogs():

    i = int(config.Config.logexpireinterval)
    i2 = int(config.Config.statslogexpireinterval)

    if i == 0 and i2 == 0:
        return

    (success, output) = execute.runLocalCmd(os.path.join(config.Config.scriptsdir, "expire-logs"))

    if not success:
        util.output("error running expire-logs\n\n")
        util.output(output)

def _checkHosts():

    for node in config.Config.hosts():
        if execute.isLocal(node):
            continue

        tag = "alive-%s" % node.host.lower()
        alive = execute.isAlive(node.addr) and "1" or "0"

        if tag in config.Config.state:
            previous = config.Config.state[tag]

            if alive != previous:
                plugin.Registry.hostStatusChanged(node.host, alive == "1")
                util.output("host %s %s" % (node.host, alive == "1" and "up" or "down"))

        config.Config._setState(tag, alive)


def _updateHTTPStats():
    # Create meta file.
    if not os.path.exists(config.Config.statsdir):
        try:
            os.makedirs(config.Config.statsdir)
        except OSError, err:
            util.output("error creating directory: %s" % err)
            return

        util.warn("creating directory for stats file: %s" % config.Config.statsdir)

    metadat = os.path.join(config.Config.statsdir, "meta.dat")
    try:
        meta = open(metadat, "w")
    except IOError, err:
        util.output("error creating file: %s" % err)
        return

    for node in config.Config.hosts():
        print >>meta, "node", node, node.type, node.host

    print >>meta, "time", time.asctime()
    print >>meta, "version", config.Config.version

    try:
        print >>meta, "os", execute.runLocalCmd("uname -a")[1][0]
    except IndexError:
        print >>meta, "os <error>"

    try:
        print >>meta, "host", execute.runLocalCmd("hostname")[1][0]
    except IndexError:
        print >>meta, "host <error>"

    meta.close()

    wwwdir = os.path.join(config.Config.statsdir, "www")
    if not os.path.isdir(wwwdir):
        try:
            os.makedirs(wwwdir)
        except OSError, err:
            util.output("failed to create directory: %s" % err)
            return

    # Append the current stats.log in spool to the one in ${statsdir}
    dst = os.path.join(config.Config.statsdir, os.path.basename(config.Config.statslog))
    try:
        fdst = open(dst, "a")
    except IOError, err:
        util.output("failed to append to file: %s" % err)
        return

    fsrc = open(config.Config.statslog, "r")
    shutil.copyfileobj(fsrc, fdst)
    fdst.close()
    fsrc.close()

    # Update the WWW data
    statstocsv = os.path.join(config.Config.scriptsdir, "stats-to-csv")

    (success, output) = execute.runLocalCmd("%s %s %s %s" % (statstocsv, config.Config.statslog, metadat, wwwdir))
    if not success:
        util.output("stats-to-csv failed")
        return

    os.unlink(config.Config.statslog)
    shutil.copy(metadat, wwwdir)

