# These modules provides a set of functions to execute actions on a host.
# If the host is local, it's done direcly; if it's remote we log in via SSH.

import os
import sys
import socket
import shutil
import time
import subprocess

import config
import util

haveBroccoli = True

try:
    import broccoli
except ImportError:
    haveBroccoli = False

LocalAddrs = None

# Wrapper around subprocess.Popen()
def popen(cmdline, stderr_to_stdout=False, donotcaptureoutput=False):

    if donotcaptureoutput:
        stdout = None
        stderr = None
    else:
        stdout = subprocess.PIPE
        stderr = subprocess.PIPE

    if stderr_to_stdout:
        stderr = subprocess.STDOUT

    # os.setsid makes sure that the child process doesn't receive our CTRL-Cs.
    proc = subprocess.Popen([cmdline], stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                            close_fds=True, shell=True, preexec_fn=os.setsid)

    return proc

# Returns true if given node corresponds to the host we're running on.
def isLocal(node):
    global LocalAddrs
    if not LocalAddrs:
        (success, output) = runLocalCmd(os.path.join(config.Config.scriptsdir, "local-interfaces"))
        if not success:
            util.warn("cannot get list of local IP addresses")

            try:
                LocalAddrs = ["127.0.0.1", "::1"]
                addrinfo = socket.getaddrinfo(socket.gethostname(), None, 0, 0, socket.SOL_TCP)
                for ai in addrinfo:
                    LocalAddrs.append(ai[4][0])
            except:
                LocalAddrs = ["127.0.0.1", "::1"]
        else:
            LocalAddrs = [line.strip() for line in output]

        util.debug(1, "Local IPs: %s" % ",".join(LocalAddrs))

    return not node or node.host == "localhost" or node.addr in LocalAddrs

# Takes list of (node, dir) pairs and ensures the directories exist on the nodes' host.
# Returns list of (node, sucess) pairs.
def mkdirs(dirs):

    results = []
    cmds = []
    fullcmds = []

    for (node, dir) in dirs:
        # We make local directories directly.
        if isLocal(node):
            if not exists(node, dir):
                util.debug(1, "mkdir -p %s" % dir, prefix="local")
                os.makedirs(dir)

            results += [(node, True)]

        else:
            cmds += [(node, [], [])]
            # Need to be careful here as our helper scripts may not be installed yet.
            fullcmds += [("test -d %s || mkdir -p %s 2>/dev/null; echo $?; echo ~~~" % (dir, dir))]

    for (node, success, output) in runHelperParallel(cmds, fullcmds=fullcmds):
        results += [(node, success)]

    return results

# Takes list of (node, dir) pairs and ensures the directories exist on the nodes' host.
# Returns list of (node, sucess) pairs.
def mkdir(node, dir):
    return mkdirs([(node, dir)])[0][1]

def rmdirs(dirs):
    results = []
    cmds = []

    for (node, dir) in dirs:
        # We remove local directories directly.
        if isLocal(node):
            (success, output) = runLocalCmd("rm -rf %s" % dir)
            results += [(node, success)]
        else:
            cmds += [(node, "rmdir", [dir])]

    for (node, success, output) in runHelperParallel(cmds):
        results += [(node, success)]

    return results

# Removes the directory on the host if it's there.
def rmdir(node, dir):
    return rmdirs([(node, dir)])[0][1]

# Returns true if the path exists on the host.
def exists(host, path):
    if isLocal(host):
        return os.path.lexists(path)
    else:
        (success, output) = runHelper(host, "exists", [path])
        return success

# Returns true if the path exists and refers to a file on the host.
def isfile(host, path):
    if isLocal(host):
        return os.path.isfile(path)
    else:
        util.error("isfile() not yet supported for remote hosts")

# Returns true if the path exists and refers to a directory on the host.
def isdir(host, path):
    if isLocal(host):
        return os.path.isdir(path)
    else:
        (success, output) = runHelper(host, "is-dir", [path])
        return success

# Copies src to dst, preserving permission bits, but does not clobber existing
# files/directories.
# Works for files and directories (recursive).
def install(host, src, dstdir):
    if isLocal(host):
        if not exists(host, src):
            util.output("file does not exist: %s" % src)
            return False

        dst = os.path.join(dstdir, os.path.basename(src))
        if exists(host, dst):
            # Do not clobber existing files/dirs (this is not an error)
            return True

        util.debug(1, "cp %s %s" % (src, dstdir))

        try:
            if os.path.isfile(src):
                shutil.copy2(src, dstdir)
            elif os.path.isdir(src):
                shutil.copytree(src, dst)
        except OSError:
            # Python 2.6 has a bug where this may fail on NFS. So we just
            # ignore errors.
            pass

    else:
        util.error("install() not yet supported for remote hosts")

    return True

# rsyncs paths from localhost to destination hosts.
def sync(nodes, paths):
    result = True
    cmds = []
    for n in nodes:
        args = ["-rRl", "--delete", "--rsh=\"ssh -o ConnectTimeout=30\""]
        dst = ["%s:/" % util.formatRsyncAddr(util.scopeAddr(n.host))]
        args += paths + dst
        cmdline = "rsync %s" % " ".join(args)
        cmds += [(n, cmdline, "", None)]

    for (id, success, output) in runLocalCmdsParallel(cmds):
        if not success:
            util.warn("error rsyncing to %s: %s" % (util.scopeAddr(id.host), output))
            result = False

    return result

# Keep track of hosts that are not alive.
_deadHosts = {}

# Return true if the given host is alive (i.e., we can establish
# an ssh session), and false otherwise.
def isAlive(host):

    if host in _deadHosts:
        return False

    (success, output) = runLocalCmd("ssh -o ConnectTimeout=30 %s true" % util.scopeAddr(host))

    if not success:
        _deadHosts[host] = True
        if config.Config.cron == "0":
            util.warn("host %s is not alive" % host)

    return success


# Runs command locally and returns tuple (success, output)
# with success being true if the command terminated with exit code 0,
# and output being the combined stdout/stderr output of the command.
def runLocalCmd(cmd, env = "", input=None, donotcaptureoutput=False):
    proc = _runLocalCmdInit("single", cmd, env, donotcaptureoutput)
    return _runLocalCmdWait(proc, input)

# Same as above but runs a set of local commands in parallel.
# Cmds is a list of (id, cmd, envs, input) tuples, where id is
# an arbitrary cookie identifying each command.
# Returns a list of (id, success, output) tuples.
def runLocalCmdsParallel(cmds):
    results = []
    running = []

    for (id, cmd, envs, input) in cmds:
        proc = _runLocalCmdInit(id, cmd, envs)
        running += [(id, proc, input)]

    for (id, proc, input) in running:
        (success, output) = _runLocalCmdWait(proc, input)
        results += [(id, success, output)]

    return results

def _runLocalCmdInit(id, cmd, env, donotcaptureoutput=False):

    if not env:
        env = ""

    cmdline = env + " " + cmd
    util.debug(1, cmdline, prefix="local")

    proc = popen(cmdline, stderr_to_stdout=True, donotcaptureoutput=donotcaptureoutput)

    return proc

def _runLocalCmdWait(proc, input):

    (out, err) = proc.communicate(input)
    rc = proc.returncode

    output = []
    if out:
        output = out.splitlines()

    util.debug(1, rc, prefix="local")

    for line in output:
        util.debug(2, "           > %s" % line, prefix="local")

    return (rc == 0, output)


# Runs arbitrary commands in parallel on nodes. Input is list of (node, cmd).
def executeCmdsParallel(cmds):
    helpers = []

    for (node, cmd) in cmds:
        for special in "|'\"":
            cmd = cmd.replace(special, "\\" + special)

        helpers += [(node, "run-cmd", [cmd])]

    return runHelperParallel(helpers)

# Runs a helper script from bin/helpers, according to the helper
# protocol.
# If fullcmd is given, this is the exact & complete command line (incl. paths).
# Otherwise, cmd is just the helper's name (wo/ path) and args are the
# arguments. Env is an optional enviroment variable of the form
# "key=val". Return value as for runLocalCmd().
# 'output' is None (vs. []) if we couldn't connect to host.
def runHelper(host, cmd=None, args=None, fullcmd=None, env = ""):
    util.disableSignals()
    try:
        status = _runHelperInit(host, cmd, args, fullcmd, env)
        if not status:
            return (False, None)

        status = _runHelperWait(status)
        if not status:
            return (False, None)

        return status

    finally:
        util.enableSignals()

# Same as above but runs commands on a set of hosts in parallel.
# Cmds is a list of (node, cmd, args) tuples.
# Fullcmds, if given, is a parallel list of full command lines.
# Envs, if given, is a parallel list of env variables.
# Returns a list of (node, success, output) tuples.
# 'output' is None (vs. []) if we couldn't connect to host.
def runHelperParallel(cmds, fullcmds = None, envs = None):

    util.disableSignals()

    try:
        results = []
        running = []

        for (node, cmd, args) in cmds:

            if fullcmds:
                fullcmd = fullcmds[0]
                fullcmds = fullcmds[1:]
            else:
                fullcmd = ""

            if envs:
                env = envs[0]
                envs = envs[1:]
            else:
                env = ""

            status = _runHelperInit(node, cmd, args, fullcmd, env)
            if status:
                running += [node]
            else:
                results += [(node, False, None)]

        for node in running:
            status =  _runHelperWait(node)
            if status:
                (success, output) = status
                results += [(node, success, output)]
            else:
                results += [(node, False, None)]

        return results

    finally:
        util.enableSignals()

# Helpers for running helpers.
#
# We keep the SSH sessions open across calls to runHelper.
Connections = {}
WhoAmI = None


# Remove connections that are closed, and clear the list of dead hosts.
def clearDeadHostConnections():
    global Connections
    global _deadHosts

    to_remove = [ nn for nn in Connections if Connections[nn].poll() != None ]

    for nn in to_remove:
        del Connections[nn]

    _deadHosts = {}


# FIXME: This is an ugly hack. The __del__ method produces
# strange unhandled exceptions in the child at termination
# of the main process. Not sure if disabling the cleanup
# altogether is a good thing but right now that's the
# only fix I can come up with.
def _emptyDel(self):
    pass
subprocess.Popen.__del__ = _emptyDel

def _getConnection(host):

    global WhoAmI
    if not WhoAmI:
        (success, output) = runLocalCmd("whoami")
        if not success:
            util.error("can't get 'whoami'")
        WhoAmI = output[0]

    if not host:
        host = config.Config.manager()

    if host.name in Connections:
        p = Connections[host.name]
        if p.poll() != None:
            # Terminated.
            global _deadHosts
            if host.host not in _deadHosts:
                _deadHosts[host.host] = True
                util.warn("connection to %s broke" % host.host)
            return None

        return (p.stdin, p.stdout)

    if isLocal(host):
        cmdline = "sh"
    else:
        # Check whether host is alive.
        if not isAlive(host.host):
            return None

        # ServerAliveInterval and ServerAliveCountMax prevents broctl from
        # hanging if a remote host is disconnected from network while an ssh
        # session is open.
        cmdline = "ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -l %s %s sh" % (WhoAmI, util.scopeAddr(host.host))

    util.debug(1, cmdline, prefix="local")

    try:
        p = popen(cmdline)
    except OSError, e:
        util.warn("cannot login into %s [IOError: %s]" % (host.host, e))
        return None

    Connections[host.name] = p
    return (p.stdin, p.stdout)

def _runHelperInit(host, cmd, args, fullcmd, env):

    c = _getConnection(host)
    if not c:
        return None

    (stdin, stdout) = c

    if not fullcmd:
        cmdline = "%s %s %s" % (env, os.path.join(config.Config.helperdir, cmd), " ".join(args))
    else:
        cmdline = fullcmd

    util.debug(1, cmdline, prefix=host.host)
    print >>stdin, cmdline
    stdin.flush()

    return host

def _runHelperWait(host):
    output = []
    while True:

        c = _getConnection(host)
        if not c:
            return None

        (stdin, stdout) = c

        line = stdout.readline().strip()
        if line == "~~~":
            break
        output += [line]

    try:
        rc = int(output[-1])
    except ValueError:
        util.warn("cannot parse exit code from helper on %s: %s" % (host.host, output[-1]))
        rc = 1

    util.debug(1, "exit code %d" % rc, prefix=host.host)

    for line in output:
        util.debug(2, "           > %s" % line, prefix=host.host)

    return (rc == 0, output[:-1])

# Broccoli communication with running nodes.

# Sends event  to a set of nodes in parallel.
#
# events is a list of tuples of the form (node, event, args, result_event).
#   node:    the destination node.
#   event:   the name of the event to send (node that receiver must subscribe to it as well).
#   args:    a list of event args; each arg must be a data type understood by the Broccoli module.
#   result_event: name of a event the node sends back. None if no event is sent back.
#
# Returns a list of tuples (node, success, results_args).
#   If success is True, result_args is a list of arguments as shipped with the result event,
#   or [] if no result_event was specified.
#   If success is False, results_args is a string with an error message.

def sendEventsParallel(events):

    results = []
    sent = []

    for (node, event, args, result_event) in events:

        if not haveBroccoli:
            results += [(node, False, "no Python bindings for Broccoli installed")]
            continue

        (success, bc) = _sendEventInit(node, event, args, result_event)
        if success and result_event:
            sent += [(node, result_event, bc)]
        else:
            results += [(node, success, bc)]

    for (node, result_event, bc) in sent:
        (success, result_args) = _sendEventWait(node, result_event, bc)
        results += [(node, success, result_args)]

    return results

def _sendEventInit(node, event, args, result_event):

    host = util.scopeAddr(node.addr)

    try:
        bc = broccoli.Connection("%s:%d" % (host, node.getPort()), broclass="control",
                                 flags=broccoli.BRO_CFLAG_ALWAYS_QUEUE, connect=False)
        bc.subscribe(result_event, _event_callback(bc))
        bc.got_result = False
        bc.connect()
    except IOError, e:
        util.debug(1, "broccoli: cannot connect", prefix=node.name)
        return (False, str(e))

    util.debug(1, "broccoli: %s(%s)" % (event, ", ".join(args)), prefix=node.name)
    bc.send(event, *args)
    return (True, bc)

def _sendEventWait(node, result_event, bc):
    # Wait until we have sent the event out.
    cnt = 0
    while bc.processInput():
        time.sleep(1)

        cnt += 1
        if cnt > int(config.Config.commtimeout):
            util.debug(1, "broccoli: timeout during send", prefix=node.name)
            return (False, "time-out")

    if not result_event:
        return (True, [])

    # Wait for reply event.
    cnt = 0
    bc.processInput()
    while not bc.got_result:
        time.sleep(1)
        bc.processInput()

        cnt += 1
        if cnt > int(config.Config.commtimeout):
            util.debug(1, "broccoli: timeout during receive", prefix=node.name)
            return (False, "time-out")

    util.debug(1, "broccoli: %s(%s)" % (result_event, ", ".join(bc.result_args)), prefix=node.name)
    return (True, bc.result_args)

def _event_callback(bc):
    def save_results(*args):
        bc.got_result = True
        bc.result_args = args
    return save_results

