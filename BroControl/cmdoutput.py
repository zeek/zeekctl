# Class to handle storing and printing output from broctl commands.

from BroControl import util

class CommandOutput:
    def __init__(self):
        self.msgs = []

    # Store an error message.  If showprefix is False, then do not include
    # the "error: " prefix in the stored message.
    def error(self, line, showprefix=True):
        if showprefix:
            self.msgs.append((0, "error: %s" % line))
        else:
            self.msgs.append((0, line))

    # Store a warning message.
    def warn(self, line):
        self.msgs.append((1, line))

    # Store an informational message.
    def info(self, line):
        self.msgs.append((2, line))

    # Append the messages from another CommandOutput object.
    def append(self, cmdout):
        self.msgs += cmdout.msgs

    # Output all messages.
    def printResults(self):
        for level, line in self.msgs:
            if level == 0:
                util.output(line)
            elif level == 1:
                util.warn(line)
            elif level == 2:
                util.output(line)

        self.msgs = []
