# Tasks which are to be done on a regular basis from cron.

import os
import time

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

    for (node, error, vals) in capstats:
        if not error:
            for (key, val) in vals.items():
                # Report if we don't see packets on an interface.
                tag = "lastpkts-%s" % node.name.lower()

                if key == "pkts":
                    if tag in config.Config.state:
                        last = float(config.Config.state[tag])
                    else:
                        last = -1.0

                    if float(val) == 0.0 and last != 0.0:
                        util.output("%s is not seeing any packets on interface %s" % (node.host, node.interface))

                    if float(val) != 0.0 and last == 0.0:
                        util.output("%s is seeing packets again on interface %s" % (node.host, node.interface))

                    config.Config._setState(tag, val)

                print >>out, t, node, "interface", key, val

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

    hadError, results = control.getDf(config.Config.nodes())
    for (node, dfs) in results.items():
        for df in dfs:
            fs = df[0]
            total = float(df[1])
            used = float(df[2])
            avail = float(df[3])
            perc = used * 100.0 / (used + avail)
            key = ("disk-space-%s%s" % (node, fs.replace("/", "-"))).lower()

            if perc > 100 - minspace:
                try:
                    if float(config.Config.state[key]) > 100 - minspace:
                        # Already reported.
                        continue
                except KeyError:
                    pass

                util.output("Disk space low on %s:%s - %.1f%% used." % (node, fs, perc))

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

def _getProfLogs():
    cmds = []

    for node in config.Config.hosts():
        if execute.isLocal(node):
            continue

        if not execute.isAlive(node.addr):
            continue

        cmd = os.path.join(config.Config.scriptsdir, "get-prof-log") + " %s %s %s/prof.log" % (node.name, node.host, node.cwd())
        cmds += [(node, cmd, [], None)]

    for (node, success, output) in execute.runLocalCmdsParallel(cmds):
        if not success:
            util.output("cannot get prof.log from %s" % node.name)

def _updateHTTPStats():
    # Get the prof.logs.

    # FIXME: Disabled for now. This currently copies the complete prof.log
    # each time. As these can get huge, that can take a while. We should
    # change that to only copy the most recent chunk and then also expire old
    # prof logs on the manager.
    # _getProfLogs()

    # Create meta file.
    if not os.path.exists(config.Config.statsdir):
        try:
            os.makedirs(config.Config.statsdir)
        except OSError, err:
            util.output("error creating directory: %s" % err)
            return

        util.warn("creating directory for stats file: %s" % config.Config.statsdir)

    try:
        meta = open(os.path.join(config.Config.statsdir, "meta.dat"), "w")
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

    # Run the update-stats script.
    (success, output) = execute.runLocalCmd(os.path.join(config.Config.scriptsdir, "update-stats"))

    if not success:
        util.output("error running update-stats\n\n")
        util.output(output)



