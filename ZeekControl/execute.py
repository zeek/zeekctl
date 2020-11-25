# These modules provides a set of functions to execute actions on a host.
# If the host is local, it's done direcly; if it's remote we log in via SSH.

import os
import shutil
import subprocess
import logging

from ZeekControl import ssh_runner
from ZeekControl import util


# Copy src to dstdir, preserving permission bits and file type.  The src
# file type can be symlink, regular file, or directory (directories are copied
# recursively).  If the target pathname already exists, it is not clobbered.
def install(src, dstdir, cmdout):
    if not os.path.lexists(src):
        cmdout.error("pathname not found: %s" % src)
        return False

    dst = os.path.join(dstdir, os.path.basename(src))
    if os.path.lexists(dst):
        # Do not clobber existing files/dirs (this is not an error)
        return True

    logging.debug("cp %s %s", src, dstdir)

    try:
        if os.path.islink(src):
            target = os.readlink(src)
            os.symlink(target, dst)
        elif os.path.isfile(src):
            shutil.copy2(src, dstdir)
        elif os.path.isdir(src):
            shutil.copytree(src, dst, symlinks=True)
        else:
            cmdout.error("failed to copy %s: not a file, dir, or symlink" % src)
            return False
    except OSError:
        # Python 2.6 has a bug where this may fail on NFS. So we just
        # ignore errors.
        pass
    except IOError as err:
        cmdout.error("failed to copy: %s" % err)
        return False

    return True

# rsyncs paths from localhost to destination hosts.
def sync(nodes, paths, cmdout):
    result = True
    cmds = []
    for n in nodes:
        args = ['-rRl', '--delete', '--rsh="ssh -o BatchMode=yes -o LogLevel=error -o ConnectTimeout=30"']
        dst = ["%s:/" % util.format_rsync_addr(n.addr)]
        args += paths + dst
        cmdline = "rsync %s" % " ".join(args)
        cmds += [(n, cmdline, "", None)]

    for (id, success, output) in run_localcmds(cmds):
        if not success:
            cmdout.error("rsync to %s failed: %s" % (id.addr, output))
            result = False

    return result


# Runs command locally and returns tuple (success, output)
# with success being true if the command terminated with exit code 0,
# and output is a string containing the combined stdout/stderr output of the
# command.
# The "env" is a space-separated string of environment variables to set,
# and "inputtext" is a string to send to stdin.
def run_localcmd(cmd, env=None, inputtext=None):
    proc = _run_localcmd_init("single", cmd, env)
    return _run_localcmd_wait(proc, inputtext)

# Same as run_localcmd() but runs a set of local commands in parallel.
# Cmds is a list of (id, cmd, envs, inputtext) tuples, where id is
# an arbitrary cookie identifying each command.
# Returns a list of (id, success, output) tuples.
def run_localcmds(cmds):
    results = []
    running = []

    for (id, cmd, envs, inputtext) in cmds:
        proc = _run_localcmd_init(id, cmd, envs)
        running += [(id, proc, inputtext)]

    for (id, proc, inputtext) in running:
        success, output = _run_localcmd_wait(proc, inputtext)
        results += [(id, success, output)]

    return results

def _run_localcmd_init(id, cmd, env):

    if env:
        cmdline = env + " " + cmd
    else:
        cmdline = cmd

    logging.debug(cmdline)

    # os.setsid makes sure that the child process doesn't receive our CTRL-Cs.
    proc = subprocess.Popen([cmdline], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            close_fds=True, shell=True, preexec_fn=os.setsid)

    return proc

def _run_localcmd_wait(proc, inputtext):
    if inputtext:
        inputtext = inputtext.encode()

    # Note: "output" is combined stdout/stderr output.
    output, _ = proc.communicate(inputtext)
    rc = proc.returncode

    output = output.decode()

    logging.debug("exit status: %d", rc)

    return (rc == 0, output)


# FIXME: This is an ugly hack. The __del__ method produces
# strange unhandled exceptions in the child at termination
# of the main process. Not sure if disabling the cleanup
# altogether is a good thing but right now that's the
# only fix I can come up with.
def _emptyDel(self):
    pass
subprocess.Popen.__del__ = _emptyDel



class Executor:
    def __init__(self, config):
        self.config = config
        self.sshrunner = ssh_runner.MultiMasterManager(config.localaddrs)

    def finish(self):
        self.sshrunner.shutdown_all()

    # Run commands in parallel on one or more hosts.
    #
    # cmds:  a list of the form: [ (node, cmd, args), ... ]
    #   where "cmd" is a string, "args" is a list of strings.
    # shell:  if True, then the "cmd" (and "args") will be interpreted by a
    #   shell.
    # helper:  if True, then the "cmd" will be modified to specify the full
    #   path to the zeekctl helper script.
    #
    # Returns a list of results: [(node, success, output), ...]
    #   where "success" is a boolean (True if command's exit status was zero),
    #   and "output" is a string containing the command's stdout followed by
    #   stderr, or an error message if no result was received (this could occur
    #   upon failure to communicate with remote host, or if the command being
    #   executed did not finish before the timeout).
    def run_cmds(self, cmds, shell=False, helper=False):
        results = []

        if not cmds:
            return results

        dd = {}
        hostlist = []
        for nodecmd in cmds:
            host = nodecmd[0].addr
            if host not in dd:
                dd[host] = []
                hostlist.append(host)
            dd[host].append(nodecmd)

        nodecmdlist = []
        for host in hostlist:
            for zeeknode, cmd, args in dd[host]:
                if helper:
                    cmdargs = [os.path.join(self.config.helperdir, cmd)]
                else:
                    cmdargs = [cmd]

                if shell:
                    if args:
                        cmdargs = ["%s %s" % (cmdargs[0], " ".join(args))]
                else:
                    cmdargs += args

                nodecmdlist.append((zeeknode.addr, cmdargs))
                logging.debug("%s: %s", zeeknode.host, " ".join(cmdargs))

        for host, result in self.sshrunner.exec_multihost_commands(nodecmdlist, shell, self.config.commandtimeout):
            nodecmd = dd[host].pop(0)
            zeeknode = nodecmd[0]
            if not isinstance(result, Exception):
                res = result[0]
                out = result[1]
                err = result[2]
                results.append((zeeknode, res == 0, out + err))
                logging.debug("%s: exit code %d", zeeknode.host, res)
            else:
                results.append((zeeknode, False, str(result)))

        return results

    # Run shell commands in parallel on one or more hosts.
    # cmdlines:  a list of the form [ (node, cmdline), ... ]
    #   where "cmdline" is a string to be interpreted by the shell
    #
    # Return value is same as run_cmds.
    def run_shell_cmds(self, cmdlines):
        cmds = [(node, cmdline, []) for node, cmdline in cmdlines]

        return self.run_cmds(cmds, shell=True)

    # A convenience function that calls run_cmds.
    def run_helper(self, cmds, shell=False):
        return self.run_cmds(cmds, shell, True)

    # A convenience function that calls run_cmds.
    # dirs:  a list of the form [ (node, dir), ... ]
    #
    # Returns a list of the form: [ (node, success, output), ... ]
    #   where "success" is a boolean (true if specified directory was created
    #   or already exists).
    def mkdirs(self, dirs):
        results = []
        cmds = []

        for (node, dir) in dirs:
            cmds += [(node, "mkdir", ["-p", dir])]

        for (node, success, output) in self.run_cmds(cmds):
            results += [(node, success, output)]

        return results

    # A convenience function that calls run_cmds to remove directories
    # on one or more hosts.
    # dirs:  a list of the form [ (node, dir), ... ]
    #
    # Returns a list of the form: [ (node, success, output), ... ]
    #   where "success" is a boolean (true if specified directory was removed
    #   or does not exist).
    def rmdirs(self, dirs):
        results = []
        cmds = []

        for (node, dir) in dirs:
            cmds += [(node, "if [ -d %s ]; then rm -rf %s ; fi" % (dir, dir), [])]

        for (node, success, output) in self.run_cmds(cmds, shell=True):
            results += [(node, success, output)]

        return results

    def host_status(self):
        return self.sshrunner.host_status()

