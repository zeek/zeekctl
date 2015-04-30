# These modules provides a set of functions to execute actions on a host.
# If the host is local, it's done direcly; if it's remote we log in via SSH.

import os
import socket
import shutil
import subprocess
import logging

from BroControl import ssh_runner
from BroControl import util


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


# Copies src to dst, preserving permission bits, but does not clobber existing
# files/directories.
# Works for files and directories (recursive).
def install(src, dstdir, cmdout):
    if not os.path.lexists(src):
        cmdout.error("file does not exist: %s" % src)
        return False

    dst = os.path.join(dstdir, os.path.basename(src))
    if os.path.lexists(dst):
        # Do not clobber existing files/dirs (this is not an error)
        return True

    logging.debug("cp %s %s" % (src, dstdir))

    try:
        if os.path.isfile(src):
            shutil.copy2(src, dstdir)
        elif os.path.isdir(src):
            shutil.copytree(src, dst)
    except OSError:
        # Python 2.6 has a bug where this may fail on NFS. So we just
        # ignore errors.
        pass

    return True

# rsyncs paths from localhost to destination hosts.
def sync(nodes, paths, cmdout):
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
            cmdout.error("rsync to %s failed: %s" % (util.scopeAddr(id.host), output))
            result = False

    return result


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

    if env:
        cmdline = env + " " + cmd
    else:
        cmdline = cmd

    logging.debug(cmdline)

    proc = popen(cmdline, stderr_to_stdout=True, donotcaptureoutput=donotcaptureoutput)

    return proc

def _runLocalCmdWait(proc, input):

    (out, err) = proc.communicate(input)
    rc = proc.returncode

    output = []
    if out:
        output = out.splitlines()

    for line in output:
        logging.debug("    > %s" % line)

    logging.debug("exit status: %d" % rc)

    return (rc == 0, output)


# FIXME: This is an ugly hack. The __del__ method produces
# strange unhandled exceptions in the child at termination
# of the main process. Not sure if disabling the cleanup
# altogether is a good thing but right now that's the
# only fix I can come up with.
def _emptyDel(self):
    pass
subprocess.Popen.__del__ = _emptyDel


# Returns a list of the IP addresses associated with local interfaces.
# For IPv6 addresses, zone_id and prefix length are removed if present.
def get_local_addrs(cmdout):
    try:
        # On Linux, ifconfig is often not in the user's standard PATH.
        proc = subprocess.Popen(["PATH=$PATH:/sbin:/usr/sbin ifconfig", "-a"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        out, err = proc.communicate()
        cmdfail = proc.returncode != 0
    except OSError:
        cmdfail = True

    if cmdfail:
        cmdout.output("cannot get list of local IP addresses")

        try:
            localaddrs = ["127.0.0.1", "::1"]
            addrinfo = socket.getaddrinfo(socket.gethostname(), None, 0, 0, socket.SOL_TCP)
            for ai in addrinfo:
                localaddrs.append(ai[4][0])
        except:
            localaddrs = ["127.0.0.1", "::1"]
    else:
        localaddrs = []
        for line in out.splitlines():
            fields = line.split()
            if "inet" in fields or "inet6" in fields:
                addrfield = False
                for field in fields:
                    if field == "inet" or field == "inet6":
                        addrfield = True
                    elif addrfield and field != "addr:":
                        locaddr = field
                        # remove "addr:" prefix (if any)
                        if field.startswith("addr:"):
                            locaddr = field[5:]
                        elif field.startswith("Adresse:"):
                            locaddr = field[8:]
                        # remove everything after "/" or "%" (if any)
                        locaddr = locaddr.split("/")[0]
                        locaddr = locaddr.split("%")[0]
                        if "Adresse" in locaddr:
                            raise RuntimeError("stop here")
                        localaddrs.append(locaddr)
                        break

    return localaddrs


class Executor:
    def __init__(self, ui, localaddrs, helperdir):
        self.sshrunner = ssh_runner.MultiMasterManager(ui, localaddrs)
        self.helperdir = helperdir

    # Run commands in parallel on one or more hosts.
    #
    # cmds:  a list of the form: [ (node, cmd, args), ... ]
    #   where "cmd" is a string, "args" is a list of strings.
    # shell:  if True, then the "cmd" (and "args") will be interpreted by a
    #   shell.
    # helper:  if True, then the "cmd" will be modified to specify the full
    #   path to the broctl helper script.
    #
    # Returns a list of results: [(node, success, output), ...]
    #   where "success" is a boolean (True if command's exit status was zero),
    #   and "output" is a list of strings (stdout followed by stderr) or None
    #   if no result was received (this could occur upon failure to communicate
    #   with remote host, or if the command being executed did not finish
    #   before the timeout).
    def runCmdsParallel(self, cmds, shell=False, helper=False):
        results = []

        if not cmds:
            return results

        dd = {}
        for nodecmd in cmds:
            host = nodecmd[0].host
            if host not in dd:
                dd[host] = []
            dd[host].append(nodecmd)

        sshcmds = []
        for key in dd:
            for nodecmd in dd[key]:
                sshhost = nodecmd[0].host
                if helper:
                    sshcmdargs = [os.path.join(self.helperdir, nodecmd[1])]
                else:
                    sshcmdargs = [nodecmd[1]]

                if shell:
                    sshcmdargs = [sshcmdargs[0] + " " + " ".join(nodecmd[2])]
                else:
                    sshcmdargs += nodecmd[2]

                sshcmds.append((sshhost, sshcmdargs))
                logging.debug(sshhost + ": " + " ".join(sshcmdargs))

        for host, result in self.sshrunner.exec_multihost_commands(sshcmds, shell):
            bronode = dd[host][0][0]
            if type(result) != Exception:
                res = result[0]
                out = result[1].splitlines()
                err = result[2].splitlines()
                results.append( (bronode, res == 0, out + err) )
                logging.debug("%s: exit code %d" % (bronode.host, res))
            else:
                results.append( (bronode, False, None) )
            del dd[host][0]

        return results

    # Run shell commands in parallel on one or more hosts.
    # cmdlines:  a list of the form [ (node, cmdline), ... ]
    #   where "cmdline" is a string to be interpreted by the shell
    #
    # Return value is same as runCmdsParallel.
    def runShellCmdsParallel(self, cmdlines):
        cmds = [ (node, cmdline, []) for node, cmdline in cmdlines ]

        return self.runCmdsParallel(cmds, shell=True)

    # A convenience function that calls runCmdsParallel.
    def runHelperParallel(self, cmds, shell=False):
        return self.runCmdsParallel(cmds, shell, True)

    # A convenience function that calls runHelperParallel for one command on
    # one node.
    #
    # Returns a tuple of the form: (success, output)
    #   where "success" is a boolean (true if command's exit status was zero),
    #   and "output" is a list of strings (stdout followed by stderr) or None
    #   if no result was received (this could occur upon failure to communicate
    #   with remote host, or if the command being executed did not finish
    #   before the timeout).
    def runHelper(self, node, cmd, args):
        cmds = [(node, cmd, args)]
        results = self.runHelperParallel(cmds)
        return (results[0][1], results[0][2])

    # A convenience function that calls runCmdsParallel.
    # dirs:  a list of the form [ (node, dir), ... ]
    #
    # Returns a list of the form: [ (node, success), ... ]
    #   where "success" is a boolean (true if specified directory was created
    #   or already exists).
    def mkdirs(self, dirs):
        results = []
        cmds = []

        for (node, dir) in dirs:
            cmds += [(node, "mkdir", ["-p", dir])]

        for (node, success, output) in self.runCmdsParallel(cmds):
            results += [(node, success)]

        return results

    # A convenience function that calls mkdirs for one directory on one node.
    # Returns a boolean (true if specified directory was created or already
    # exists).
    def mkdir(self, node, dir):
        return self.mkdirs([(node, dir)])[0][1]

    # A convenience function that calls runCmdsParallel to remove directories
    # on one or more hosts.
    # dirs:  a list of the form [ (node, dir), ... ]
    #
    # Returns a list of the form: [ (node, success), ... ]
    #   where "success" is a boolean (true if specified directory was removed
    #   or does not exist).
    def rmdirs(self, dirs):
        results = []
        cmds = []

        for (node, dir) in dirs:
            cmds += [(node, "if [ -d %s ]; then rm -rf %s ; fi" % (dir, dir), [])]

        for (node, success, output) in self.runCmdsParallel(cmds, shell=True):
            results += [(node, success)]

        return results

    # A convenience function that calls rmdirs for one directory on one node.
    # Returns a boolean (true if specified directory was removed or does not
    # exist).
    def rmdir(self, node, dir):
        return self.rmdirs([(node, dir)])[0][1]

    # A convenience function that calls runCmdsParallel to check if a directory
    # on a node exists.
    #
    # Returns a boolean (true if specified path exists and is a directory).
    def isdir(self, node, path):
        cmds = [(node, "test", ["-d", "%s" % path])]

        results = self.runCmdsParallel(cmds)

        return results[0][1]

