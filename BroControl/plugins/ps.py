#
# A simple example plugin implementing a command "ps.bro" that shows all Bro
# processes currently running on any of the configured nodes, including  those
# not controlled by this broctl. The latter are marked with "(-)", while "our"
# processes get a "(+)".

import BroControl.plugin

class PsBro(BroControl.plugin.Plugin):
    def __init__(self):
        super(PsBro, self).__init__(apiversion=1)

    def name(self):
        return "ps"

    def pluginVersion(self):
        return 1

    def commands(self):
        return [("bro", "[<nodes>]", "Show Bro processes on nodes' systems")]

    def cmd_custom(self, cmd, args):

        assert(cmd == "bro") # Can't be anything else.

        # Get the nodes the user wants.
        if args:
            nodes = self.parseNodes(args)
        else:
            nodes = self.nodes()

        if not nodes:
            self.message("No nodes given.")
            return

        # Get one node for every host running at least one of the nodes. Also
        # records each hosts Bro PIDs.
        host_nodes = {}
        pids = {}

        for n in nodes:
            pid = n.getPID()
            if pid:
                p = pids.setdefault(n.host, set())
                p.add(pid)

            host_nodes[n.host] = n

        # Build commands to execute.

        cmd = "POSIXLY_CORRECT=1 ps axco user,pid,ppid,%cpu,%mem,vsz,rss,tt,state,start,time,command | grep -e PID -e 'bro$'"
        cmds = [(n, cmd) for n in host_nodes.values()]
        cmds.sort(key=lambda n: n[0].name)

        # Run them in parallel and print output.

        def startNode(n, success, output, first_node):
            # Note: output might be None or an empty list, in which case we
            # still want the "failed" message below.
            if first_node and output:
                print "       ", output[0]

            if not success:
                print ">>>", n.host, "failed"
            else:
                print ">>>", n.host


        first_node = True

        for (n, success, output) in self.executeParallel(cmds):
            # Remove stderr output (if any)
            while output and not output[0].startswith("USER"):
                output = output[1:]

            startNode(n, success, output, first_node)

            if not output:
                continue

            for line in output[1:]:

                m = line.split()
                (pid, ppid) = (int(m[1]), int(m[2]))
                try:
                    known = (pid in pids[n.host] or ppid in pids[n.host])
                except KeyError:
                    known = False

                if known:
                    print "   (+)", line.strip()
                else:
                    print "   (-)", line.strip()

            first_node = False
