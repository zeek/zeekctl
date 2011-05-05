#
# A simple example plugin implementing a command "ps.bro" that shows all Bro
# processes currently running on any of the configured nodes, including  those
# not controlled by this broctl. The latter are marked with "(-)", while "our"
# processes get a "(+)".

import BroControl.plugin

class TestPlugin(BroControl.plugin.Plugin):

    def name(self):
        return "ps"

    def version(self):
        return 1

    def commands(self):
        return [("bro", "[<nodes>]", "Shows Bro processes currently running on nodes' systems.")]

    def cmd_custom(self, cmd, args):

        assert(cmd == "bro") # Can't be anything else.

        # Get the nodes the user wants.
        nodes = self.parseNodes(args) if args else self.nodes()

        if not nodes:
            self.message("No nodes given.")
            return

        # Get one node for every host running at least one of the nodes. Also
        # records each hosts Bro PIDs.
        host_nodes = {}
        pids = {}

        for n in nodes:
            host = n.host
            pid = n.getPID()
            if pid:
                p = pids.setdefault(n.host, set())
                p.add(pid)

            host_nodes[n.host] = n

        # Build commands to execute.

        cmd = "POSIXLY_CORRECT=1 ps axco user,pid,ppid,%cpu,%mem,vsz,rss,tt,state,start,time,command | grep 'PID\\\\|bro$'"
        cmds = [(n, cmd) for n in host_nodes.values()]

        # Run them in parallel and print output.
        for (n, success, output) in self.executeParallel(cmds):
            if not success:
                print ">>>", n.host, "failed"
            else:
                print ">>>", n.host

            print "       ", output[0]

            for line in output[1:]:
                m = line.split()
                (pid, ppid) = (int(m[1]), int(m[2]))
                known = (pid in pids[n.host] or ppid in pids[n.host])
                print "   ", "(+)" if known else "(-)", line.strip()

