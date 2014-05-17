# Functions to control the nodes' operations.

import os
import time

import execute
import util
import cmdoutput
import config
import cron
import install
import plugin
import node as node_mod

# Convert a number into a string with a unit (e.g., 1024 into "1M").
def prettyPrintVal(val):
    for (prefix, unit, factor) in (("", "G", 1024*1024*1024), ("", "M", 1024*1024), ("", "K", 1024)):
        if val >= factor:
            return "%s%3.0f%s" % (prefix, val / factor, unit)
    return " %3.0f" % (val)

# Checks multiple nodes in parallel and returns list of tuples (node, isrunning).
def isRunning(nodes, cmdout, setcrashed=True):

    results = []
    cmds = []

    for node in nodes:
        pid = node.getPID()
        if not pid:
            results += [(node, False)]
            continue

        cmds += [(node, "check-pid", [str(pid)])]

    for (node, success, output) in execute.runHelperParallel(cmds, cmdout):

        # If we cannot connect to the host at all, we filter it out because
        # the process might actually still be running but we can't tell.
        if output == None:
            if config.Config.cron == "0":
                cmdout.error("cannot connect to %s" % node.name)
            continue

        results += [(node, success)]

        if not success:
            if setcrashed:
                # Grmpf. It crashed.
                node.clearPID()
                node.setCrashed()

    return results

# For a list of (node, bool), returns True if at least one boolean is False.
def nodeFailed(nodes):
    for (node, success) in nodes:
        if not success:
            return True
    return False

# Waits for the nodes' Bro processes to reach the given status.
def waitForBros(nodes, status, timeout, ensurerunning, cmdout):

    # If ensurerunning is true, process must still be running.
    if ensurerunning:
        running = isRunning(nodes, cmdout)
    else:
        running = [(node, True) for node in nodes]

    results = []

    # Determine set of nodes still to check.
    todo = {}
    for (node, isrunning) in running:
        if isrunning:
            todo[node.name] = node
        else:
            results += [(node, False)]

    while True:
        # Determine  whether process is still running. We need to do this
        # before we get the state to avoid a race condition.
        running = isRunning(todo.values(), cmdout, setcrashed=False)

        # Check nodes' .status file
        cmds = []
        for node in todo.values():
            cmds += [(node, "cat-file", ["%s/.status" % node.cwd()])]

        for (node, success, output) in execute.runHelperParallel(cmds, cmdout):
            if success:
                try:
                    (stat, loc) = output[0].split()
                    if status in stat:
                        # Status reached. Cool.
                        del todo[node.name]
                        results += [(node, True)]
                except IndexError:
                    # Something's wrong. We give up on that node.
                    del todo[node.name]
                    results += [(node, False)]

        for (node, isrunning) in running:
            if node.name in todo and not isrunning:
                # Alright, a dead node's status will not change anymore.
                del todo[node.name]
                results += [(node, False)]

        if not todo:
            # All done.
            break

        # Wait a bit before we start over.
        time.sleep(1)

        # Timeout reached?
        timeout -= 1
        if timeout <= 0:
            break

        util.debug(1, "Waiting for %d node(s)..." % len(todo))

    for node in todo.values():
        # These did time-out.
        results += [(node, False)]

    if todo:
        util.debug(1, "Timeout while waiting for %d node(s)" % len(todo))

    return results

# Build the Bro parameters for the given node. Include
# script for live operation if live is true.
def _makeBroParams(node, live):
    args = []

    if live and node.interface:
        try:
            # If interface name contains semicolons (to aggregate traffic from
            # multiple devices with PF_RING, the interface name can be in a
            # semicolon-delimited format, such as "p2p1;p2p2"), then we must
            # quote it to prevent shell from interpreting semicolon as command
            # separator.
            args += ["-i \"%s\"" % node.interface]
        except AttributeError:
            pass

        if config.Config.savetraces == "1":
            args += ["-w trace.pcap"]

    args += ["-U .status"]
    args += ["-p broctl"]

    if live:
        args += ["-p broctl-live"]

    if node.type == "standalone":
        args += ["-p standalone"]

    for p in config.Config.prefixes.split(":"):
        args += ["-p %s" % p]

    args += ["-p %s" % node.name]

    # The order of loaded scripts is as follows:
    # 1) local.bro gives a common set of loaded scripts for all nodes.
    # 2) The common configuration of broctl is loaded via the broctl package.
    # 3) The distribution's default settings for node configuration are loaded
    #    from either the cluster framework or standalone scripts.  This also
    #    involves loading local-<node>.bro scripts.  At this point anything
    #    in the distribution's default per-node is overridable and any
    #    identifiers in local.bro are able to be used (e.g. in defining
    #    a notice policy).
    # 4) Autogenerated broctl scripts are loaded, which may contain
    #    settings that override the previously loaded node-specific scripts.
    #    (e.g. Log::default_rotation_interval is set in manager.bro,
    #    but overrided by broctl.cfg)
    args += config.Config.sitepolicystandalone.split()
    args += ["broctl"]
    if node.type == "standalone":
        args += ["broctl/standalone"]
    else:
        args += ["base/frameworks/cluster"]
        if node.type == "manager":
            args += config.Config.sitepolicymanager.split()
        elif node.type == "proxy":
            args += ["local-proxy"]
        elif node.type == "worker":
            args += config.Config.sitepolicyworker.split()
    args += ["broctl/auto"]

    if "aux_scripts" in node.__dict__:
        args += [node.aux_scripts]

    if config.Config.broargs:
        args += [config.Config.broargs]

#   args += ["-B comm,serial"]

    return args

# Build the environment variable for the given node.
def _makeEnvParam(node):
    env = ""
    if node.type != "standalone":
        env += "CLUSTER_NODE=%s" % node.name

    vars = " ".join(["%s=%s" % (key, val) for (key, val) in sorted(node.env_vars.items())])

    if vars:
        env += " " + vars

    return env

# Do a "post-terminate crash" for the given nodes.
def _makeCrashReports(nodes, cmdout):

    for n in nodes:
        plugin.Registry.broProcessDied(n)

    msg = "If you want to help us debug this problem, then please forward\nthis mail to reports@bro.org\n"
    cmds = []
    for node in nodes:
        cmds += [(node, "run-cmd",  [os.path.join(config.Config.scriptsdir, "post-terminate"), node.cwd(),  "crash"])]

    for (node, success, output) in execute.runHelperParallel(cmds, cmdout):
        if not success:
            cmdout.error("cannot run post-terminate for %s" % node.name)
        else:
            if not util.sendMail("Crash report from %s" % node.name, msg + "\n".join(output)):
                cmdout.error("cannot send mail")

        node.clearCrashed()

# Starts the given nodes.
def _startNodes(nodes, cmdout):
    results = []

    filtered = []
    # Ignore nodes which are still running.
    for (node, isrunning) in isRunning(nodes, cmdout):
        if not isrunning:
            filtered += [node]
            if node.hasCrashed():
                cmdout.info("starting %s (was crashed) ..." % node.name)
            else:
                cmdout.info("starting %s ..." % node.name)
        else:
            cmdout.info("%s still running" % node.name)

    nodes = filtered

    # Generate crash report for any crashed nodes.
    crashed = [node for node in nodes if node.hasCrashed()]
    _makeCrashReports(crashed, cmdout)

    # Make working directories.
    dirs = [(node, node.cwd()) for node in nodes]
    nodes = []
    for (node, success) in execute.mkdirs(dirs, cmdout):
        if success:
            nodes += [node]
        else:
            cmdout.error("cannot create working directory for %s" % node.name)
            results += [(node, False)]

    # Start Bro process.
    cmds = []
    envs = []
    for node in nodes:
        pin_cpu = node.pin_cpus

        # If this node isn't using CPU pinning, then use a placeholder value
        if pin_cpu == "":
            pin_cpu = -1

        cmds += [(node, "start", [node.cwd(), str(pin_cpu)] + _makeBroParams(node, True))]
        envs += [_makeEnvParam(node)]

    nodes = []
    for (node, success, output) in execute.runHelperParallel(cmds, cmdout, envs=envs):
        if success:
            nodes += [node]
            node.setPID(int(output[0]))
        else:
            cmdout.error("cannot start %s; check output of \"diag\"" % node.name)
            results += [(node, False)]

    # Check whether processes did indeed start up.
    hanging = []
    running = []

    for (node, success) in waitForBros(nodes, "RUNNING", 3, True, cmdout):
        if success:
            running += [node]
        else:
            hanging += [node]

    # It can happen that Bro hangs in DNS lookups at startup
    # which can take a while. At this point we already know
    # that the process has been started (waitForBro ensures that).
    # If by now there is not a TERMINATED status, we assume that it
    # is doing fine and will move on to RUNNING once DNS is done.
    for (node, success) in waitForBros(hanging, "TERMINATED", 0, False, cmdout):
        if success:
            cmdout.error("%s terminated immediately after starting; check output with \"diag\"" % node.name)
            node.clearPID()
            results += [(node, False)]
        else:
            cmdout.info("(%s still initializing)" % node.name)
            running += [node]

    for node in running:
        cron.logAction(node, "started")
        results += [(node, True)]

    return results

# Start Bro processes on nodes if not already running.
def start(nodes, cmdout):
    manager = []
    proxies = []
    workers = []

    for n in nodes:
        if n.type == "worker":
            workers += [n]
        elif n.type == "proxy":
            proxies += [n]
        else:
            manager += [n]

    # Start nodes. Do it in the order manager, proxies, workers.

    results1 = _startNodes(manager, cmdout)

    if nodeFailed(results1):
        return (results1 + [(n, False) for n in (proxies + workers)], cmdout)

    results2 = _startNodes(proxies, cmdout)

    if nodeFailed(results2):
        return (results1 + results2 + [(n, False) for n in workers], cmdout)

    results3 = _startNodes(workers, cmdout)

    return results1 + results2 + results3

def _stopNodes(nodes, cmdout):

    results = []
    running = []

    # Check for crashed nodes.
    for (node, isrunning) in isRunning(nodes, cmdout):
        if isrunning:
            running += [node]
            cmdout.info("stopping %s ..." % node.name)
        else:
            results += [(node, True)]

            if node.hasCrashed():
                cmdout.info("%s not running (was crashed)" % node.name)
                _makeCrashReports([node], cmdout)
            else:
                cmdout.info("%s not running" % node.name)

    # Helper function to stop nodes with given signal.
    def stop(nodes, signal):
        cmds = []
        for node in nodes:
            cmds += [(node, "stop", [str(node.getPID()), str(signal)])]

        return execute.runHelperParallel(cmds, cmdout)
        #events = []
        #for node in nodes:
        #    events += [(node, "Control::shutdown_request", [], "Control::shutdown_response")]
        #return execute.sendEventsParallel(events)

    # Stop nodes.
    for (node, success, output) in stop(running, 15):
        if not success:
            cmdout.error("failed to send stop signal to %s" % node.name)

    if running:
        time.sleep(1)

    # Check whether they terminated.
    terminated = []
    kill = []
    for (node, success) in waitForBros(running, "TERMINATED", int(config.Config.stoptimeout), False, cmdout):
        if not success:
            # Check whether it crashed during shutdown ...
            result = isRunning([node], cmdout)
            for (node, isrunning) in result:
                if isrunning:
                    cmdout.info("%s did not terminate ... killing ..." % node.name)
                    kill += [node]
                else:
                    # crashed flag is set by isRunning().
                    cmdout.info("%s crashed during shutdown" % node.name)

    if kill:
        # Kill those which did not terminate gracefully.
        stop(kill, 9)
        # Give them a bit to disappear.
        time.sleep(5)

    # Check which are still running. We check all nodes to be on the safe side
    # and give them a bit more time to finally disappear.
    timeout = 10

    todo = {}
    for node in running:
        todo[node.name] = node

    while True:

        running = isRunning(todo.values(), cmdout, setcrashed=False)

        for (node, isrunning) in running:
            if node.name in todo and not isrunning:
                # Alright, it's gone.
                del todo[node.name]
                terminated += [node]
                results += [(node, True)]

        if not todo:
            # All done.
            break

        # Wait a bit before we start over.

        if timeout <= 0:
            break

        time.sleep(1)
        timeout -= 1

    results += [(node, False) for node in todo]

    # Do post-terminate cleanup for those which terminated gracefully.
    cleanup = [node for node in terminated if not node.hasCrashed()]

    cmds = []
    for node in cleanup:
        crashflag = ""
        if node in kill:
            crashflag = "killed"

        cmds += [(node, "run-cmd",  [os.path.join(config.Config.scriptsdir, "post-terminate"), node.cwd(), crashflag])]

    for (node, success, output) in execute.runHelperParallel(cmds, cmdout):
        if not success:
            cmdout.error("cannot run post-terminate for %s" % node.name)
            cron.logAction(node, "stopped (failed)")
        else:
            cron.logAction(node, "stopped")

        node.clearPID()
        node.clearCrashed()

    return results

# Stop Bro processes on nodes.
def stop(nodes):
    cmdout = cmdoutput.CommandOutput()
    manager = []
    proxies = []
    workers = []

    for n in nodes:
        if n.type == "worker":
            workers += [n]
        elif n.type == "proxy":
            proxies += [n]
        else:
            manager += [n]


    # Stop nodes. Do it in the order workers, proxies, manager
    # (the reverse of "start").

    results1 = _stopNodes(workers, cmdout)

    if nodeFailed(results1):
        return (results1 + [(n, False) for n in (proxies + manager)], cmdout)

    results2 = _stopNodes(proxies, cmdout)

    if nodeFailed(results2):
        return (results1 + results2 + [(n, False) for n in manager], cmdout)

    results3 = _stopNodes(manager, cmdout)

    return (results1 + results2 + results3, cmdout)

# Output status summary for nodes.
def status(nodes, cmdout):

    result = []

    all = isRunning(nodes, cmdout)
    running = []

    cmds1 = []
    cmds2 = []
    for (node, isrunning) in all:
        if isrunning:
            running += [node]
            cmds1 += [(node, "cat-file", ["%s/.startup" % node.cwd()])]
            cmds2 += [(node, "cat-file", ["%s/.status" % node.cwd()])]

    cmdout.info("Getting bro process status..")
    startups = execute.runHelperParallel(cmds1, cmdout)
    statuses = execute.runHelperParallel(cmds2, cmdout)

    startups = dict([(n.name, success and util.fmttime(output[0]) or "???") for (n, success, output) in startups])
    statuses = dict([(n.name, success and output[0].split()[0].lower() or "???") for (n, success, output) in statuses])

    peers = {}
    nodes = [n for n in running if statuses[n.name] == "running"]
    cmdout.info("Getting bro peer status..")
    for (node, success, args) in _queryPeerStatus(nodes, cmdout):
        if success:
            peers[node.name] = []
            for f in args[0].split():
                keyval = f.split("=")
                if len(keyval) > 1:
                    (key, val) = keyval
                    if key == "peer" and val != "":
                        peers[node.name] += [val]
        else:
            peers[node.name] = None

    for (node, isrunning) in all:
        node_info = {
            'name': node.name,
            'type': node.type,
            'host': node.host,
            "status": "stopped",
            "pid": None,
            "peers": None,
            "started": None,
        }
        if isrunning:
            node_info['status'] = statuses[node.name]
        elif node.hasCrashed():
            node_info['status'] = "crashed"

        if isrunning:
            node_info["pid"] = node.getPID()

            if node.name in peers and peers[node.name] != None:
                node_info["peers"] = len(peers[node.name])

            node_info["started"] = startups[node.name]

        result.append(node_info)

    # Return status code of True only if all nodes are running
    return result


# Returns a list of tuples of the form (node, error, vals) where 'error' is an
# error message string, or None if there was no error.  'vals' is a list of
# dicts which map tags to their values.  Tags are "pid", "proc", "vsize",
# "rss", "cpu", and "cmd".
#
# We do all the stuff in parallel across all nodes which is why this looks
# a bit confusing ...
def getTopOutput(nodes, cmdout):

    results = []
    cmds = []

    running = isRunning(nodes, cmdout)

    # Get all the PIDs first.

    pids = {}
    parents = {}

    for (node, isrunning) in running:
        if isrunning:
            pid = node.getPID()
            pids[node.name] = [pid]
            parents[node.name] = str(pid)

            cmds += [(node, "get-childs", [str(pid)])]
        else:
            results += [(node, "not running", [{}])]
            continue

    if not cmds:
        return results

    for (node, success, output) in execute.runHelperParallel(cmds, cmdout):

        if not success:
            results += [(node, "cannot get child pids", [{}])]
            continue

        pids[node.name] += [int(line) for line in output]

    cmds = []
    hosts = {}

    # Now run top once per host.
    for node in nodes:   # Do the loop again to keep the order.
        if node.name not in pids:
            continue

        if node.host in hosts:
            continue

        hosts[node.host] = 1

        cmds += [(node, "top", [])]

    if not cmds:
        return results

    res = {}
    for (node, success, output) in execute.runHelperParallel(cmds, cmdout):
        res[node.host] = (success, output)

    # Gather results for all the nodes that are running
    for node in nodes:
        if node.name not in pids:
            continue

        success, output = res[node.host]

        if not success or not output:
            results += [(node, "cannot get top output", [{}])]
            continue

        procs = [line.split() for line in output if int(line.split()[0]) in pids[node.name]]

        if not procs:
            # It's possible that the process is no longer there.
            results += [(node, "not running", [{}])]
            continue

        vals = []

        try:
            for p in procs:
                d = {}
                d["pid"] = int(p[0])
                d["proc"] = (p[0] == parents[node.name] and "parent" or "child")
                d["vsize"] = long(float(p[1])) #May be something like 2.17684e+9
                d["rss"] = long(float(p[2]))
                d["cpu"] = p[3]
                d["cmd"] = " ".join(p[4:])
                vals += [d]
        except ValueError, err:
            results += [(node, "unexpected top output: %s" % err, [{}])]
            continue

        results += [(node, None, vals)]

    return results

# Produce a top-like output for node's processes.
def top(nodes):
    cmdout = cmdoutput.CommandOutput()
    typewidth = 7
    hostwidth = 16
    if config.Config.standalone == "1":
        # In standalone mode, we need a wider "type" column.
        typewidth = 10
        hostwidth = 13

    cmdout.info("%-12s %-*s %-*s %-7s %-7s %-6s %-5s %-4s %s" % ("Name", typewidth, "Type", hostwidth, "Host", "Pid", "Proc", "VSize", "Rss", "Cpu", "Cmd"))

    cmdSuccess = True
    for (node, error, vals) in getTopOutput(nodes, cmdout):

        if not error:
            for d in vals:
                msg = [ "%-12s" % node.name ]
                msg.append("%-*s" % (typewidth, node.type))
                msg.append("%-*s" % (hostwidth, node.host))
                msg.append("%-7s" % d["pid"])
                msg.append("%-7s" % d["proc"])
                msg.append("%-6s" % prettyPrintVal(d["vsize"]))
                msg.append("%-5s" % prettyPrintVal(d["rss"]))
                msg.append("%-4s" % ("%s%%" % d["cpu"]))
                msg.append("%s" % d["cmd"])
                cmdout.info(" ".join(msg))
        else:
            cmdSuccess = False
            msg = [ "%-12s" % node.name ]
            msg.append("%-*s" % (typewidth, node.type))
            msg.append("%-*s" % (hostwidth, node.host))
            msg.append("<%s>" % error)
            cmdout.error(" ".join(msg), False)

    return (cmdSuccess, cmdout)

def _doCheckConfig(nodes, cmdout, installed, list_scripts):
    results = []

    manager = config.Config.manager()

    all = [(node, os.path.join(config.Config.tmpdir, "check-config-%s" % node.name)) for node in nodes]

    if not os.path.exists(os.path.join(config.Config.scriptsdir, "broctl-config.sh")):
        cmdout.error("broctl-config.sh not found (try 'broctl install')")
        # Return a failure for one node to indicate that the command failed
        results += [(all[0][0], False)]
        return results

    nodes = []
    for (node, cwd) in all:
        if os.path.isdir(cwd):
            if not execute.rmdir(config.Config.manager(), cwd, cmdout):
                cmdout.error("cannot remove directory %s on manager" % cwd)
                results += [(node, False)]
                continue

        if not execute.mkdir(config.Config.manager(), cwd, cmdout):
            cmdout.error("cannot create directory %s on manager" % cwd)
            results += [(node, False)]
            continue

        nodes += [(node, cwd)]

    cmds = []
    for (node, cwd) in nodes:

        env = _makeEnvParam(node)

        installed_policies = installed and "1" or "0"
        print_scripts = list_scripts and "1" or "0"

        install.makeLayout(cwd, cmdout, True)
        install.makeLocalNetworks(cwd, cmdout, True)
        install.makeConfig(cwd, cmdout, True)

        cmd = os.path.join(config.Config.scriptsdir, "check-config") + " %s %s %s %s" % (installed_policies, print_scripts, cwd, " ".join(_makeBroParams(node, False)))
        cmd += " broctl/check"

        cmds += [((node, cwd), cmd, env, None)]

    for ((node, cwd), success, output) in execute.runLocalCmdsParallel(cmds):
        results += [(node, success)]
        if success:
            cmdout.info("%s scripts are ok." % node.name)
            if list_scripts:
                for line in output:
                    cmdout.info("  %s" % line)
        else:
            cmdout.error("%s scripts failed." % node.name)
            for line in output:
                cmdout.error("   %s" % line)

        execute.rmdir(manager, cwd, cmdout)

    return results

# Check the configuration for nodes without installing first.
def checkConfigs(nodes, cmdout):
    return _doCheckConfig(nodes, cmdout, False, False)

# Prints the loaded_scripts.log for either the installed scripts
# (if check argument is false), or the original scripts (if check arg is true)
def listScripts(nodes, check):
    return _doCheckConfig(nodes, not check, True)

# Report diagostics for node (e.g., stderr output).
def crashDiag(node):
    cmdout = cmdoutput.CommandOutput()

    cmdout.info("[%s]" % node.name)

    if not execute.isdir(node, node.cwd(), cmdout):
        cmdout.error("No work dir found\n")
        return (False, cmdout)

    (rc, output) = execute.runHelper(node, cmdout, "run-cmd",  [os.path.join(config.Config.scriptsdir, "crash-diag"), node.cwd()])
    if not rc:
        cmdout.error("cannot run crash-diag for %s" % node.name)
        return (False, cmdout)

    for line in output:
        cmdout.info(line)

    return (True, cmdout)

# Clean up the working directory for nodes (flushes state).
# If cleantmp is true, also wipes ${tmpdir}; this is done
# even when the node is still running.
def cleanup(nodes, cleantmp=False, cmdout=cmdoutput.CommandOutput()):
    cmdSuccess = True

    cmdout.info("cleaning up nodes ...")
    result = isRunning(nodes, cmdout)
    running =    [node for (node, on) in result if on]
    notrunning = [node for (node, on) in result if not on]

    results1 = execute.rmdirs([(n, n.cwd()) for n in notrunning], cmdout)
    results2 = execute.mkdirs([(n, n.cwd()) for n in notrunning], cmdout)
    if nodeFailed(results1) or nodeFailed(results2):
        cmdSuccess = False

    for node in notrunning:
        node.clearCrashed()

    for node in running:
        cmdout.info("   %s is still running, not cleaning work directory" % node.name)

    if cleantmp:
        results3 = execute.rmdirs([(n, config.Config.tmpdir) for n in running + notrunning], cmdout)
        results4 = execute.mkdirs([(n, config.Config.tmpdir) for n in running + notrunning], cmdout)
        if nodeFailed(results3) or nodeFailed(results4):
            cmdSuccess = False

    return cmdSuccess

# Attach gdb to the main Bro processes on the given nodes.
def attachGdb(nodes):
    cmdout = cmdoutput.CommandOutput()
    running = isRunning(nodes, cmdout)

    cmds = []
    cmdSuccess = True
    for (node, isrunning) in running:
        if isrunning:
            cmds += [(node, "gdb-attach", ["gdb-%s" % node.name, config.Config.bro, str(node.getPID())])]
        else:
            cmdSuccess = False

    results = execute.runHelperParallel(cmds, cmdout)
    for (node, success, output) in results:
        if success:
            cmdout.info("gdb attached on %s" % node.name)
        else:
            cmdout.error("cannot attach gdb on %s: %s" % node.name, output)
            cmdSuccess = False

    return (cmdSuccess, cmdout)

# Gather capstats from interfaces.
#
# Returns a list of tuples of the form (node, error, vals) where 'error' is
# None if we were able to get the data, or otherwise a string with an error
# message; in case there's no error, 'vals' maps tags to their values.
#
# Tags are those as returned by capstats on the command-line.
#
# If there is more than one node, then the results will also contain
# one "pseudo-node" of the name "$total" with the sum of all individual values.
#
# We do all the stuff in parallel across all nodes which is why this looks
# a bit confusing ...
def getCapstatsOutput(nodes, interval, cmdout):

    results = []

    hosts = {}
    for node in nodes:
        if not node.interface:
            continue

        try:
            hosts[(node.addr, node.interface)] = node
        except AttributeError:
            continue

    cmds = []

    for (addr, interface) in hosts.keys():
        node = hosts[addr, interface]

        # If interface name contains semicolons (to aggregate traffic from
        # multiple devices with PF_RING, the interface name can be in a
        # semicolon-delimited format, such as "p2p1;p2p2"), then we must
        # quote it to prevent shell from interpreting semicolon as command
        # separator (another layer of quotes is needed because the eval
        # command is used).
        capstats = [config.Config.capstatspath, "-I", str(interval), "-n", "1", "-i", "'\"%s\"'" % interface]

        cmds += [(node, "run-cmd", capstats)]

    outputs = execute.runHelperParallel(cmds, cmdout)

    totals = {}

    for (node, success, output) in outputs:

        if not success:
            if output:
                results += [(node, "%s: capstats failed (%s)" % (node.name, output[0]), {})]
            else:
                results += [(node, "%s: cannot execute capstats" % node.name, {})]
            continue

        if not output:
            results += [(node, "%s: no capstats output" % node.name, {})]
            continue

        fields = output[0].split()[1:]

        if not fields:
            results += [(node, "%s: unexpected capstats output: %s" % (node.name, output[0]), {})]
            continue

        vals = {}

        try:
            for field in fields:
                (key, val) = field.split("=")
                val = float(val)
                vals[key] = val

                if key in totals:
                    totals[key] += val
                else:
                    totals[key] = val

            results += [(node, None, vals)]

        except ValueError:
            results += [(node, "%s: unexpected capstats output: %s" % (node.name, output[0]), {})]

    # Add pseudo-node for totals
    if len(nodes) > 1:
        results += [(node_mod.Node("$total"), None, totals)]

    return results

# Get current statistics from cFlow.
#
# Returns dict of the form port->(cum-pkts, cum-bytes).
#
# Returns None if we can't run the helper sucessfully.
def getCFlowStatus(cmdout):
    (success, output) = execute.runLocalCmd(os.path.join(config.Config.scriptsdir, "cflow-stats"))
    if not success or not output:
        cmdout.error("failed to run cflow-stats")
        return None

    vals = {}

    for line in output:
        try:
            (port, pps, bps, pkts, bytes) = line.split()
            vals[port] = (float(pkts), float(bytes))
        except ValueError:
            # Probably an error message because we can't connect.
            cmdout.error("failed to get cFlow statistics: %s" % line)
            return None

    return vals

# Calculates the differences between to getCFlowStatus() calls.
# Returns a list of tuples in the same form as getCapstatsOutput() does.
def calculateCFlowRate(start, stop, interval):
    diffs = [(port, stop[port][0] - start[port][0], (stop[port][1] - start[port][1])) for port in start.keys() if port in stop]

    rates = []
    for (port, pkts, bytes) in diffs:
        vals = { "kpps": "%.1f" % (pkts / 1e3 / interval) }
        if start[port][1] >= 0:
            vals["mbps"] = "%.1f" % (bytes * 8 / 1e6 / interval)

        rates += [(port, None, vals)]

    return rates

def capstats(nodes, interval):

    def output(tag, data, cout):

        def outputOne(tag, vals):
            return "%-21s %-10s %s" % (tag, vals.get("kpps", ""), vals.get("mbps", ""))


        cout.info("\n%-21s %-10s %-10s (%ds average)\n%s" % (tag, "kpps", "mbps", interval, "-" * 40))

        totals = None

        for (port, error, vals) in sorted(data):

            if error:
                cout.error(error)
                continue

            if str(port) != "$total":
                cout.info(outputOne(port, vals))
            else:
                totals = vals

        if totals:
            cout.info("")
            cout.info(outputOne("Total", totals))
            cout.info("")


    cmdout_capstats = cmdoutput.CommandOutput()
    cmdout_cflow = cmdoutput.CommandOutput()
    cmdSuccess = True

    have_cflow = config.Config.cflowaddress and config.Config.cflowuser and config.Config.cflowpassword
    have_capstats = config.Config.capstatspath

    if not have_cflow and not have_capstats:
        cmdout_capstats.error("capstats binary is not available")
        return (False, cmdout_capstats, cmdout_cflow)

    if have_cflow:
        cflow_start = getCFlowStatus(cmdout_cflow)
        if not cflow_start:
            cmdSuccess = False

    if have_capstats:
        capstats = []
        for (node, error, vals) in getCapstatsOutput(nodes, interval, cmdout_capstats):
            if str(node) == "$total":
                capstats += [(node, error, vals)]
            else:
                capstats += [("%s/%s" % (node.host, node.interface), error, vals)]

            if error:
                cmdSuccess = False

    else:
        time.sleep(interval)

    if have_cflow:
        cflow_stop = getCFlowStatus(cmdout_cflow)
        if not cflow_stop:
            cmdSuccess = False

    if have_capstats:
        output("Interface", capstats, cmdout_capstats)

    if have_cflow and cflow_start and cflow_stop:
        diffs = calculateCFlowRate(cflow_start, cflow_stop, interval)
        output("cFlow Port", diffs, cmdout_cflow)

    return (cmdSuccess, cmdout_capstats, cmdout_cflow)

# Update the configuration of a running instance on the fly.
def update(nodes):
    cmdout = cmdoutput.CommandOutput()

    running = isRunning(nodes, cmdout)
    zone = config.Config.zoneid
    if not zone:
        zone = "NOZONE"

    cmds = []
    for (node, isrunning) in running:
        if isrunning:
            env = _makeEnvParam(node)
            env += " BRO_DNS_FAKE=1"
            args = " ".join(_makeBroParams(node, False))
            cmds += [(node.name, os.path.join(config.Config.scriptsdir, "update") + " %s %s %s/tcp %s" % (util.formatBroAddr(node.addr), zone, node.getPort(), args), env, None)]
            cmdout.info("updating %s ..." % node.name)

    results = execute.runLocalCmdsParallel(cmds)

    for (tag, success, output) in results:
        if not success:
            cmdout.error("could not update %s: %s" % (tag, output))
        else:
            cmdout.info("%s: %s" % (tag, output[0]))

    return ([(config.Config.nodes(tag=tag)[0], success) for (tag, success, output) in results], cmdout)

# Gets disk space on all volumes relevant to broctl installation.
# Returns a list of the form:  [ (host, diskinfo), ...]
# where diskinfo is a list of the form [fs, total, used, avail, perc] or
# ["FAIL", <error message>] if an error is encountered.
def getDf(nodes, cmdout):
    dirs = ("logdir", "bindir", "helperdir", "cfgdir", "spooldir", "policydir", "libdir", "tmpdir", "staticdir", "scriptsdir")

    df = {}
    for node in nodes:
        df["%s/%s" % (node.name, node.host)] = {}

    for dir in dirs:
        path = config.Config.config[dir]

        cmds = []
        for node in nodes:
            if dir == "logdir" and node.type != "manager":
                # Don't need this on the workers/proxies.
                continue

            cmds += [(node, "df", [path])]

        results = execute.runHelperParallel(cmds, cmdout)

        for (node, success, output) in results:
            nodehost = "%s/%s" % (node.name, node.host)
            if success:
                if output:
                    fields = output[0].split()

                    # Ignore NFS mounted volumes.
                    if fields[0].find(":") < 0:
                        total = float(fields[1])
                        used = float(fields[2])
                        avail = float(fields[3])
                        perc = used * 100.0 / (used + avail)
                        df[nodehost][fields[0]] = [fields[0], total, used,
                                                   avail, perc]
                else:
                    df[nodehost]["FAIL"] = ["FAIL", "no output from df helper"]
            else:
                if output:
                    msg = output[0]
                else:
                    msg = "unknown failure"
                df[nodehost]["FAIL"] = ["FAIL", msg]

    result = []
    for node in nodes:
        nodehost = "%s/%s" % (node.name, node.host)
        result.append((nodehost, df[nodehost].values()))

    return result

def df(nodes):
    cmdout = cmdoutput.CommandOutput()
    cmdSuccess = True

    cmdout.info("%27s  %15s  %-5s  %-5s  %-5s" % ("", "", "total", "avail", "capacity"))

    results = getDf(nodes, cmdout)

    for (node, dfs) in results:
        for df in dfs:
            if df[0] == "FAIL":
                cmdSuccess = False
                cmdout.error("df helper failed on %s: %s" % (node, df[1]))
                continue

            (fs, total, used, avail, perc) = df

            cmdout.info("%27s  %15s  %-5s  %-5s  %-5.1f%%" % (node,
                fs, prettyPrintVal(total), prettyPrintVal(avail), perc))

    return (cmdSuccess, cmdout)


def printID(nodes, id):
    cmdout = cmdoutput.CommandOutput()
    cmdSuccess = True

    running = isRunning(nodes, cmdout)

    events = []
    for (node, isrunning) in running:
        if isrunning:
            events += [(node, "Control::id_value_request", [id], "Control::id_value_response")]

    results = execute.sendEventsParallel(events)

    for (node, success, args) in results:
        if success:
            cmdout.info("%12s   %s = %s" % (node, args[0], args[1]))
        else:
            cmdout.error("%12s   <error: %s>" % (node, args))
            cmdSuccess = False

    return (cmdSuccess, cmdout)

def _queryPeerStatus(nodes, cmdout):
    running = isRunning(nodes, cmdout)

    events = []
    for (node, isrunning) in running:
        if isrunning:
            events += [(node, "Control::peer_status_request", [], "Control::peer_status_response")]

    return execute.sendEventsParallel(events)

def _queryNetStats(nodes, cmdout):
    running = isRunning(nodes, cmdout)

    events = []
    for (node, isrunning) in running:
        if isrunning:
            events += [(node, "Control::net_stats_request", [], "Control::net_stats_response")]

    return execute.sendEventsParallel(events)

def peerStatus(nodes):
    cmdout = cmdoutput.CommandOutput()
    cmdSuccess = True

    for (node, success, args) in _queryPeerStatus(nodes, cmdout):
        if success:
            cmdout.info("%11s" % node)
            cmdout.info(args[0])
        else:
            cmdout.error("%11s   <error: %s>" % (node, args))
            cmdSuccess = False

    return (cmdSuccess, cmdout)

def netStats(nodes):
    cmdout = cmdoutput.CommandOutput()
    cmdSuccess = True

    for (node, success, args) in _queryNetStats(nodes, cmdout):
        if success:
            cmdout.info("%11s: %s" % (node, args[0].strip()))
        else:
            cmdout.error("%11s: <error: %s>" % (node, args))
            cmdSuccess = False

    return (cmdSuccess, cmdout)

def executeCmd(nodes, cmd, cmdout):
    return execute.executeCmdsParallel([(n, cmd) for n in nodes], cmdout)

def processTrace(trace, bro_options, bro_scripts):
    cmdout = cmdoutput.CommandOutput()

    if not os.path.isfile(trace):
        cmdout.error("trace file not found: %s" % trace)
        return (False, cmdout)

    if not os.path.exists(os.path.join(config.Config.scriptsdir, "broctl-config.sh")):
        cmdout.error("broctl-config.sh not found (try 'broctl install')")
        return (False, cmdout)

    standalone = (config.Config.standalone == "1")
    if standalone:
        tag = "standalone"
    else:
        tag = "workers"

    node = config.Config.nodes(tag=tag)[0]

    cwd = os.path.join(config.Config.tmpdir, "testing")

    if not execute.rmdir(config.Config.manager(), cwd, cmdout):
        cmdout.error("cannot remove directory %s on manager" % cwd)
        return (False, cmdout)

    if not execute.mkdir(config.Config.manager(), cwd, cmdout):
        cmdout.error("cannot create directory %s on manager" % cwd)
        return (False, cmdout)

    env = _makeEnvParam(node)

    bro_args =  " ".join(bro_options + _makeBroParams(node, False))
    bro_args += " broctl/process-trace"

    if bro_scripts:
        bro_args += " " + " ".join(bro_scripts)

    cmd = os.path.join(config.Config.scriptsdir, "run-bro-on-trace") + " %s %s %s %s" % (0, cwd, trace, bro_args)

    cmdout.info(cmd)

    (success, output) = execute.runLocalCmd(cmd, env, donotcaptureoutput=True)

    for line in output:
        cmdout.info(line)

    cmdout.info("")
    cmdout.info("### Bro output in %s" % cwd)

    return (success, cmdout)

