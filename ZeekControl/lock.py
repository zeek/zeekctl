import os
import time

from ZeekControl import config

lockCount = 0

# Return: 0 if no lock, >0 for PID of lock, or -1 on error
def _break_lock(cmdout):
    from ZeekControl import execute

    try:
        # Check whether lock is stale.
        with open(config.Config.lockfile, "r") as f:
            pid = f.readline().strip()

    except (OSError, IOError) as err:
        cmdout.error("failed to read lock file: %s" % err)
        return -1

    success, output = execute.run_localcmd("%s %s" % (os.path.join(config.Config.helperdir, "check-pid"), pid))
    if success and output.strip() == "running":
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
