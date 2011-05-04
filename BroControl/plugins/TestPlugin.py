#
# A simple test plugin exercising most of a plugins capabilities. It just does
# some debugging output, nothing else.
#

import BroControl.plugin

class TestPlugin(BroControl.plugin.Plugin):

    def name(self):
        return "TestPlugin"

    def prefix(self):
        return "test"

    def version(self):
        return 1

    def init(self):
        foo = self.getOption("foo")

        self.message("Test initialized")
        self.message("The value of foo is: %s" % foo)
        self.message("The current value of bar is: %s" % self.getState("bar"))

        for n in self.nodes():
            self.message("mykey is: %s" % n.test_mykey)

        for h in self.hosts():
            self.message("host %s" % h)

        return True

    def options(self):
        return [("foo", "string", "1", "Just a test option.")]

    def commands(self):
        return [("bar", "A test command from the Test plugin.")]

    def nodeKeys(self):
        return ["mykey"]

    def analyses(self):
        return [("foobar", "Just a dummy test analysis.", ("unload", "icmp"))]

    def _nodes(self, nodes):

        if not nodes:
            return "<empty>"

        if isinstance(nodes[0], tuple):
            nodes = [n[0] for n in nodes]

        return ",".join([str(n) for n in nodes])

    def _results(self, results):

        if not results:
            return "<empty>"

        if isinstance(results[0], tuple):
            results = [n[0] for n in results]

        return ",".join(["%s/%s" % (str(n[0]), n[1]) for n in results])

    def cmd_custom(self, cmd, args):

        bar = self.getState("bar")
        if not bar:
            bar = "1"

        self.setState("bar", str(int(bar) + 1))
        self.message("My command: %s" % args)

    def cmd_check_pre(self, nodes):
        self.message("Test pre 'check':  %s" % self._nodes(nodes))

    def cmd_check_post(self, nodes):
        self.message("Test post 'check': %s" % self._nodes(nodes))

    def cmd_nodes_pre(self):
        self.message("Test pre 'nodes'")

    def cmd_nodes_post(self):
        self.message("Test post 'nodes'")

    def cmd_config_pre(self):
        self.message("Test pre 'config'")

    def cmd_config_post(self):
        self.message("Test post 'confg'")

    def cmd_exec_pre(self, cmdline):
        self.message("Test pre 'exec':  %s" % cmdline)

    def cmd_exec_post(self, cmdline):
        self.message("Test post 'exec': %s" % cmdline)

    def cmd_install_pre(self):
        self.message("Test pre 'install'")

    def cmd_install_post(self):
        self.message("Test post 'install'")

    def cmd_cron_pre(self, arg):
        self.message("Test pre 'cron':  %s" % arg)

    def cmd_cron_post(self, arg):
        self.message("Test post 'cron': %s" % arg)

    def cmd_analysis_pre(self, enable, type):
        self.message("Test pre 'analysis':   %s %s" % (enable, type))

    def cmd_analysis_post(self, enable, type):
        self.message("Test post 'analysis':  %s %s" % (enable, type))

    def cmd_start_pre(self, nodes):
        self.message("Test pre 'start':  %s" % self._nodes(nodes))

    def cmd_start_post(self, results):
        self.message("Test post 'start': %s" % self._results(results))

    def cmd_stop_pre(self, nodes):
        self.message("Test pre 'stop':  %s" % self._nodes(nodes))

    def cmd_stop_post(self, results):
        self.message("Test post 'stop': %s" % self._results(results))

    def cmd_status_pre(self, nodes):
        self.message("Test pre 'status':  %s" % self._nodes(nodes))

    def cmd_status_post(self, nodes):
        self.message("Test post 'status': %s" % self._nodes(nodes))

    def cmd_update_pre(self, nodes):
        self.message("Test pre 'update':  %s" % self._nodes(nodes))

    def cmd_update_post(self, results):
        self.message("Test post 'update': %s" % self._results(results))

    def cmd_df_pre(self, nodes):
        self.message("Test pre 'df':  %s" % self._nodes(nodes))

    def cmd_df_post(self, nodes):
        self.message("Test post 'df': %s" % self._nodes(nodes))

    def cmd_diag_pre(self, nodes):
        self.message("Test pre 'diag':  %s" % self._nodes(nodes))

    def cmd_diag_post(self, nodes):
        self.message("Test post 'diag': %s" % self._nodes(nodes))

    def cmd_attachgdb_pre(self, nodes):
        self.message("Test pre 'attachgdb':  %s" % self._nodes(nodes))

    def cmd_attachgdb_post(self, nodes):
        self.message("Test post 'attachgdb': %s" % self._nodes(nodes))

    def cmd_peerstatus_pre(self, nodes):
        self.message("Test pre 'peerstatus':  %s" % self._nodes(nodes))

    def cmd_peerstatus_post(self, nodes):
        self.message("Test post 'peerstatus': %s" % self._nodes(nodes))

    def cmd_netstats_pre(self, nodes):
        self.message("Test pre 'netstats':  %s" % self._nodes(nodes))

    def cmd_netstats_post(self, nodes):
        self.message("Test post 'netstats': %s" % self._nodes(nodes))

    def cmd_top_pre(self, nodes):
        self.message("Test pre 'top':  %s" % self._nodes(nodes))

    def cmd_top_post(self, nodes):
        self.message("Test post 'top': %s" % self._nodes(nodes))

    def cmd_cleanup_pre(self, nodes, all):
        self.message("Test pre 'cleanup':  %s (%s)" % (self._nodes(nodes), all))

    def cmd_cleanup_post(self, nodes, all):
        self.message("Test post 'cleanup': %s (%s)" % (self._nodes(nodes), all))

    def cmd_capstats_pre(self, nodes, interval):
        self.message("Test pre 'capstats':  %s (%d)" % (self._nodes(nodes), interval))

    def cmd_capstats_post(self, nodes, interval):
        self.message("Test post 'capstats':  %s (%d)" % (self._nodes(nodes), interval))

    def cmd_scripts_pre(self, nodes, full_path, check):
        self.message("Test pre 'scripts':  %s (%s/%s)" % (self._nodes(nodes), full_path, check))

    def cmd_scripts_post(self, nodes, full_path, check):
        self.message("Test post 'scripts': %s (%s/%s)" % (self._nodes(nodes), full_path, check))

    def cmd_print_pre(self, nodes, id):
        self.message("Test pre 'print':  %s (%s)" % (self._nodes(nodes), id))

    def cmd_print_post(self, nodes, id):
        self.message("Test post 'print': %s (%s)" % (self._nodes(nodes), id))



