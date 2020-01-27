#
# A simple example plugin implementing a command "ps.zeek" that shows all Zeek
# processes currently running on any of the configured nodes, including  those
# not controlled by this zeekctl. The latter are marked with "(-)", while "our"
# processes get a "(+)".

import ZeekControl.plugin
import ZeekControl.cmdresult

class PsZeek(ZeekControl.plugin.Plugin):
    def __init__(self):
        super(PsZeek, self).__init__(apiversion=1)

    def name(self):
        return "ps"

    def pluginVersion(self):
        return 1

    def commands(self):
        return [
            ("zeek", "[<nodes>]", "Show Zeek processes on nodes' systems"),
        ]

    def cmd_custom(self, cmd, args, cmdout):
        results = ZeekControl.cmdresult.CmdResult()

        assert(cmd == "zeek") # Can't be anything else.

        # Get the nodes the user wants.
        if args:
            nodes, notnodes = self.parseNodes(args)
            for n in notnodes:
                cmdout.error("unknown node '%s'" % n)
        else:
            nodes = self.nodes()

        if not nodes:
            cmdout.error("No nodes given.")
            results.ok = False
            return results

        # Get one node for every host running at least one of the nodes. Also
        # records each hosts Zeek PIDs.
        host_nodes = {}
        pids = {}

        for n in nodes:
            pid = n.getPID()
            if pid:
                p = pids.setdefault(n.host, set())
                p.add(pid)

            host_nodes[n.host] = n

        # Build commands to execute.

        # The grep command grabs the header line and all lines ending in "zeek"
        # (and ignores "run-zeek" that may appear in the output of ps).
        cmd = "POSIXLY_CORRECT=1 ps axco user,pid,ppid,%cpu,%mem,vsz,rss,tt,state,start,time,command | grep -e PID -e '[^-]zeek$'"
        cmds = [(n, cmd) for n in host_nodes.values()]
        cmds.sort(key=lambda n: n[0].name)

        # Run them in parallel and print output.

        first_node = True

        for (n, success, output) in self.executeParallel(cmds):
            outlines = output.splitlines()
            # Remove stderr output (if any)
            while outlines and not outlines[0].startswith("USER"):
                outlines = outlines[1:]

            # Print the header line.
            if first_node and outlines:
                cmdout.info("        %s" % outlines[0])

            if success:
                cmdout.info(">>> %s" % n.host)
            else:
                cmdout.error(">>> %s failed" % n.host)
                results.ok = False

            if not outlines:
                continue

            for line in outlines[1:]:

                m = line.split()
                try:
                    pid, ppid = int(m[1]), int(m[2])
                except IndexError:
                    cmdout.error("unexpected output from ps command: %s" % line)
                    results.ok = False
                    continue
                except ValueError as err:
                    cmdout.error("%s" % err)
                    results.ok = False
                    continue
                try:
                    known = (pid in pids[n.host] or ppid in pids[n.host])
                except KeyError:
                    known = False

                if known:
                    cmdout.info("   (+) %s" % line.strip())
                else:
                    cmdout.info("   (-) %s" % line.strip())

            first_node = False

        return results

