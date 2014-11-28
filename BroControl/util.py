from __future__ import print_function
import os
import errno
import sys
import time
import signal

from BroControl import config

def fmttime(t):
    return time.strftime(config.Config.timefmt, time.localtime(float(t)))

def output(msg = "", nl = True, prefix="output"):
    nlstr = ""
    if nl:
        nlstr = "\n"
    sys.stderr.write(msg + nlstr)

def error(msg, prefix=None):
    output("error: %s" % msg, prefix=prefix)

# For a list of tuples, where second element in tuple is a bool, return True
# if at least one boolean is False.
def nodeFailed(nodes):
    for nodetuple in nodes:
        if not nodetuple[1]:
            return True
    return False


lockCount = 0

def _breakLock(cmdout):
    from BroControl import execute

    try:
        # Check whether lock is stale.
        pid = open(config.Config.lockfile, "r").readline().strip()
        (success, output) = execute.runLocalCmd("%s %s" % (os.path.join(config.Config.helperdir, "check-pid"), pid))
        if success:
            # Process still exissts.
            return False

        # Break lock.
        cmdout.info("removing stale lock")
        os.unlink(config.Config.lockfile)
        return True

    except (OSError, IOError):
        return False

def _aquireLock(cmdout):
    if not config.Config.manager():
        # Initial install.
        return True

    pid = str(os.getpid())
    tmpfile = config.Config.lockfile + "." + pid

    lockdir = os.path.dirname(config.Config.lockfile)
    if not os.path.exists(lockdir):
        cmdout.info("creating directory for lock file: %s" % lockdir)
        os.makedirs(lockdir)

    try:
        try:
            # This should be NFS-safe.
            f = open(tmpfile, "w")
            f.write("%s\n" % pid)
            f.close()

            n = os.stat(tmpfile)[3]
            os.link(tmpfile, config.Config.lockfile)
            m = os.stat(tmpfile)[3]

            if n == m-1:
                return True

            # File is locked.
            if _breakLock(cmdout):
                return _aquireLock(cmdout)

        except OSError as e:
            # File is already locked.
            if _breakLock(cmdout):
                return _aquireLock(cmdout)

        except IOError as e:
            cmdout.error("cannot acquire lock: %s" % e)
            return False

    finally:
        try:
            os.unlink(tmpfile)
        except OSError:
            pass
        except IOError:
            pass

    return False

def _releaseLock(cmdout):
    try:
        os.unlink(config.Config.lockfile)
    except OSError as e:
        cmdout.error("cannot remove lock file: %s" % e)

def lock(cmdout):
    global lockCount

    if lockCount > 0:
        # Already locked.
        lockCount += 1
        return True

    if not _aquireLock(cmdout):

        if config.Config.cron == "1":
            do_output = 0
        else:
            do_output = 2

        if do_output:
            cmdout.info("waiting for lock ...")

        count = 0
        while not _aquireLock(cmdout):
            time.sleep(1)

            count += 1
            if count > 30:
                cmdout.info("cannot get lock") # always output this one.
                return False

    lockCount = 1
    return True

def unlock(cmdout):
    global lockCount

    if lockCount == 0:
        cmdout.error("mismatched lock/unlock")
        return

    if lockCount > 1:
        # Still locked.
        lockCount -= 1
        return

    _releaseLock(cmdout)

    lockCount = 0

# Keyboard interrupt handler.
def sigIntHandler(signum, frame):
    config.Config.config["sigint"] = "1"

def enableSignals():
    pass
    #signal.signal(signal.SIGINT, sigIntHandler)

def disableSignals():
    pass
    #signal.signal(signal.SIGINT, signal.SIG_IGN)


# 'src' is the file to which the link will point, and 'dst' is the link to make
def force_symlink(src, dst):
    try:
        os.symlink(src, dst)
    except OSError as e:
        if e.errno == errno.EEXIST:
            os.remove(dst)
            os.symlink(src, dst)

# Returns an IP address string suitable for embedding in a Bro script,
# for IPv6 colon-hexadecimal address strings, that means surrounding it
# with square brackets.
def formatBroAddr(addr):
    if addr.find(':') == -1:
        return addr
    else:
        return "[" + addr + "]"

# Returns an IP prefix string suitable for embedding in a Bro script,
# for IPv6 colon-hexadecimal prefix strings, that means surrounding the
# IP address part with square brackets.
def formatBroPrefix(prefix):
    if prefix.find(':') == -1:
        return prefix
    else:
        parts = prefix.split('/')
        return "[" + parts[0] + "]" + "/" + parts[1]

# Returns an IP address string suitable for use with rsync, which requires
# encasing IPv6 addresses in square brackets, and some shells may require
# quoting the brackets.
def formatRsyncAddr(addr):
    if addr.find(':') == -1:
        return addr
    else:
        return "'[" + addr + "]'"

# Scopes a non-global IPv6 address with a zone identifier according to RFC 4007
def scopeAddr(addr):
    zoneid = config.Config.zoneid
    if addr.find(':') == -1 or zoneid == "":
        return addr
    else:
        return addr + "%" + zoneid

# Convert a number into a string with a unit (e.g., 1024 into "1K").
def prettyPrintVal(val):
    units = (("G", 1024*1024*1024), ("M", 1024*1024), ("K", 1024))
    for (unit, factor) in units:
        if val >= factor:
            return "%3.0f%s" % (val / factor, unit)
    return " %3.0f" % (val)

