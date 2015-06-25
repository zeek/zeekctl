import os
import errno
import time
import signal

from BroControl import config

def fmttime(t):
    return time.strftime(config.Config.timefmt, time.localtime(float(t)))

lockCount = 0

# Return: 0 if no lock, >0 for PID of lock, or -1 on error
def _break_lock(cmdout):
    from BroControl import execute

    try:
        # Check whether lock is stale.
        with open(config.Config.lockfile, "r") as f:
            pid = f.readline().strip()

    except (OSError, IOError) as err:
        cmdout.error("failed to read lock file: %s" % err)
        return -1

    (success, output) = execute.run_localcmd("%s %s" % (os.path.join(config.Config.helperdir, "check-pid"), pid))
    if success and output[0] == "running":
        # Process still exists.
        try:
            return int(pid)
        except ValueError:
            return -1

    cmdout.info("removing stale lock")
    try:
        # Break lock.
        os.unlink(config.Config.lockfile)
    except (OSError, IOError) as err:
        cmdout.error("failed to remove lock file: %s" % err)
        return -1

    return 0

# Return: 0 if lock is acquired, or if failed to acquire lock return >0 for
# PID of lock, or -1 on error
def _acquire_lock(cmdout):
    lockpid = -1
    pid = str(os.getpid())
    tmpfile = config.Config.lockfile + "." + pid

    lockdir = os.path.dirname(config.Config.lockfile)
    if not os.path.exists(lockdir):
        cmdout.info("creating directory for lock file: %s" % lockdir)
        os.makedirs(lockdir)

    try:
        try:
            # This should be NFS-safe.
            with open(tmpfile, "w") as f:
                f.write("%s\n" % pid)

            n = os.stat(tmpfile)[3]
            os.link(tmpfile, config.Config.lockfile)
            m = os.stat(tmpfile)[3]

            if n == m-1:
                return 0

            # File is locked.
            lockpid = _break_lock(cmdout)
            if lockpid == 0:
                return _acquire_lock(cmdout)

        except OSError:
            # File is already locked.
            lockpid = _break_lock(cmdout)
            if lockpid == 0:
                return _acquire_lock(cmdout)

        except IOError as e:
            cmdout.error("cannot acquire lock: %s" % e)
            return lockpid

    finally:
        try:
            os.unlink(tmpfile)
        except (OSError, IOError):
            pass

    return lockpid

def _release_lock(cmdout):
    try:
        os.unlink(config.Config.lockfile)
    except OSError as e:
        cmdout.error("cannot remove lock file: %s" % e)

def lock(cmdout, showwait=True):
    global lockCount

    if lockCount > 0:
        # Already locked.
        lockCount += 1
        return True

    lockpid = _acquire_lock(cmdout)
    if lockpid < 0:
        return False

    if lockpid:
        if showwait:
            cmdout.info("waiting for lock (owned by PID %d) ..." % lockpid)

        count = 0
        while _acquire_lock(cmdout) != 0:
            time.sleep(1)

            count += 1
            if count > 30:
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

    _release_lock(cmdout)

    lockCount = 0

# Keyboard interrupt handler.
def sigint_handler(signum, frame):
    pass
    #config.Config.config["sigint"] = "1"

def enable_signals():
    pass
    #signal.signal(signal.SIGINT, sigint_handler)

def disable_signals():
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
        else:
            raise

# Returns an IP address string suitable for embedding in a Bro script,
# for IPv6 colon-hexadecimal address strings, that means surrounding it
# with square brackets.
def format_bro_addr(addr):
    if ":" not in addr:
        return addr
    else:
        return "[%s]" % addr

# Returns an IP prefix string suitable for embedding in a Bro script,
# for IPv6 colon-hexadecimal prefix strings, that means surrounding the
# IP address part with square brackets.
def format_bro_prefix(prefix):
    if ":" not in prefix:
        return prefix
    else:
        parts = prefix.split("/")
        return "[%s]/%s" % (parts[0], parts[1])

# Returns an IP address string suitable for use with rsync, which requires
# encasing IPv6 addresses in square brackets, and some shells may require
# quoting the brackets.
def format_rsync_addr(addr):
    if ":" not in addr:
        return addr
    else:
        return "'[%s]'" % addr

# Scopes a non-global IPv6 address with a zone identifier according to RFC 4007
def scope_addr(addr):
    zoneid = config.Config.zoneid
    if ":" not in addr or zoneid == "":
        return addr
    else:
        return addr + "%" + zoneid

# Convert a number into a string with a unit (e.g., 1024 into "1K").
def number_unit_str(num):
    units = (("G", 1024*1024*1024), ("M", 1024*1024), ("K", 1024))
    for (unit, factor) in units:
        if num >= factor:
            return "%3.0f%s" % (num / factor, unit)
    return " %3.0f" % (num)

