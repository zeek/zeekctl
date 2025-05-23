#
# A simple test plugin exercising most of a plugins capabilities. It just does
# some debugging output, nothing else.
#
# The plugin is off by default. To enable it, add "test.enabled=1" to zeekctl.cfg.

import ZeekControl.cmdresult
import ZeekControl.plugin


class TestPlugin(ZeekControl.plugin.Plugin):
    def __init__(self):
        super().__init__(apiversion=1)

    def name(self):
        return "TestPlugin"

    def prefix(self):
        return "test"

    def pluginVersion(self):
        return 1

    def init(self):
        if not self.getOption("enabled"):
            return False

        foo = self.getOption("foo")

        self.message("TestPlugin: Test initialized")
        self.message(f"TestPlugin: The value of foo is: {foo}")
        self.message(
            "TestPlugin: The current value of bar is: {}".format(self.getState("bar"))
        )

        for n in self.nodes():
            try:
                self.message(f"TestPlugin: mykey is: {n.test_mykey}")
            except AttributeError:
                self.message("TestPlugin: mykey is not set")

        for h in self.hosts():
            self.message(f"TestPlugin: host {h.host}")

        return True

    def options(self):
        return [
            ("foo", "int", 1, "Just a test option."),
            ("enabled", "bool", False, "Set to enable plugin"),
        ]

    def commands(self):
        return [("bar", "", "A test command from the Test plugin.")]

    def nodeKeys(self):
        return ["mykey"]

    def zeekctl_config(self):
        script = "# This is a test."
        return script

    def done(self):
        self.message("TestPlugin: done")

    def _nodes(self, nodes):
        if not nodes:
            return "<empty>"

        if isinstance(nodes[0], tuple):
            nodes = [n[0] for n in nodes]

        return ",".join([str(n) for n in nodes])

    def _results(self, results):
        if not results:
            return "<empty>"

        return ",".join([f"{str(n[0])}/{n[1]}" for n in results])

    def zeekProcessDied(self, node):
        self.message(f"TestPlugin: Zeek process died for {node}")

    def hostStatusChanged(self, host, status):
        self.message(f"TestPlugin: host status changed: {host} -> {status}")

    def cmd_custom(self, cmd, args, cmdout):
        results = ZeekControl.cmdresult.CmdResult()

        bar = self.getState("bar")
        if not bar:
            bar = 1

        self.setState("bar", bar + 1)
        self.message(f"TestPlugin: My command: {args}")

        return results

    def cmd_check_pre(self, nodes):
        self.message(f"TestPlugin: Test pre 'check':  {self._nodes(nodes)}")

    def cmd_check_post(self, results):
        self.message(f"TestPlugin: Test post 'check': {self._results(results)}")

    def cmd_nodes_pre(self):
        self.message("TestPlugin: Test pre 'nodes'")
        return True

    def cmd_nodes_post(self):
        self.message("TestPlugin: Test post 'nodes'")

    def cmd_config_pre(self):
        self.message("TestPlugin: Test pre 'config'")
        return True

    def cmd_config_post(self):
        self.message("TestPlugin: Test post 'config'")

    def cmd_deploy_pre(self):
        self.message("TestPlugin: Test pre 'deploy'")
        return True

    def cmd_deploy_post(self):
        self.message("TestPlugin: Test post 'deploy'")

    def cmd_exec_pre(self, cmdline):
        self.message(f"TestPlugin: Test pre 'exec':  {cmdline}")
        return True

    def cmd_exec_post(self, cmdline):
        self.message(f"TestPlugin: Test post 'exec': {cmdline}")

    def cmd_install_pre(self):
        self.message("TestPlugin: Test pre 'install'")
        return True

    def cmd_install_post(self):
        self.message("TestPlugin: Test post 'install'")

    def cmd_cron_pre(self, arg, watch):
        self.message(f"TestPlugin: Test pre 'cron':  {arg}/{watch}")
        return True

    def cmd_cron_post(self, arg, watch):
        self.message(f"TestPlugin: Test post 'cron': {arg}/{watch}")

    def cmd_restart_pre(self, nodes, clean):
        self.message(f"TestPlugin: Test pre 'restart':  {self._nodes(nodes)} ({clean})")

    def cmd_restart_post(self, nodes):
        self.message(f"TestPlugin: Test post 'restart': {self._nodes(nodes)}")

    def cmd_start_pre(self, nodes):
        self.message(f"TestPlugin: Test pre 'start':  {self._nodes(nodes)}")

    def cmd_start_post(self, results):
        self.message(f"TestPlugin: Test post 'start': {self._results(results)}")

    def cmd_stop_pre(self, nodes):
        self.message(f"TestPlugin: Test pre 'stop':  {self._nodes(nodes)}")

    def cmd_stop_post(self, results):
        self.message(f"TestPlugin: Test post 'stop': {self._results(results)}")

    def cmd_status_pre(self, nodes):
        self.message(f"TestPlugin: Test pre 'status':  {self._nodes(nodes)}")

    def cmd_status_post(self, nodes):
        self.message(f"TestPlugin: Test post 'status': {self._nodes(nodes)}")

    def cmd_update_pre(self, nodes):
        self.message(f"TestPlugin: Test pre 'update':  {self._nodes(nodes)}")

    def cmd_update_post(self, results):
        self.message(f"TestPlugin: Test post 'update': {self._results(results)}")

    def cmd_df_pre(self, nodes):
        self.message(f"TestPlugin: Test pre 'df':  {self._nodes(nodes)}")

    def cmd_df_post(self, nodes):
        self.message(f"TestPlugin: Test post 'df': {self._nodes(nodes)}")

    def cmd_diag_pre(self, nodes):
        self.message(f"TestPlugin: Test pre 'diag':  {self._nodes(nodes)}")

    def cmd_diag_post(self, nodes):
        self.message(f"TestPlugin: Test post 'diag': {self._nodes(nodes)}")

    def cmd_peerstatus_pre(self, nodes):
        self.message(f"TestPlugin: Test pre 'peerstatus':  {self._nodes(nodes)}")

    def cmd_peerstatus_post(self, nodes):
        self.message(f"TestPlugin: Test post 'peerstatus': {self._nodes(nodes)}")

    def cmd_netstats_pre(self, nodes):
        self.message(f"TestPlugin: Test pre 'netstats':  {self._nodes(nodes)}")

    def cmd_netstats_post(self, nodes):
        self.message(f"TestPlugin: Test post 'netstats': {self._nodes(nodes)}")

    def cmd_top_pre(self, nodes):
        self.message(f"TestPlugin: Test pre 'top':  {self._nodes(nodes)}")

    def cmd_top_post(self, nodes):
        self.message(f"TestPlugin: Test post 'top': {self._nodes(nodes)}")

    def cmd_cleanup_pre(self, nodes, all):
        self.message(f"TestPlugin: Test pre 'cleanup':  {self._nodes(nodes)} ({all})")

    def cmd_cleanup_post(self, nodes, all):
        self.message(f"TestPlugin: Test post 'cleanup': {self._nodes(nodes)} ({all})")

    def cmd_capstats_pre(self, nodes, interval):
        self.message(
            f"TestPlugin: Test pre 'capstats':  {self._nodes(nodes)} ({interval})"
        )

    def cmd_capstats_post(self, nodes, interval):
        self.message(
            f"TestPlugin: Test post 'capstats':  {self._nodes(nodes)} ({interval})"
        )

    def cmd_scripts_pre(self, nodes, check):
        self.message(f"TestPlugin: Test pre 'scripts':  {self._nodes(nodes)} ({check})")

    def cmd_scripts_post(self, nodes, check):
        self.message(f"TestPlugin: Test post 'scripts': {self._nodes(nodes)} ({check})")

    def cmd_print_pre(self, nodes, id):
        self.message(f"TestPlugin: Test pre 'print':  {self._nodes(nodes)} ({id})")

    def cmd_print_post(self, nodes, id):
        self.message(f"TestPlugin: Test post 'print': {self._nodes(nodes)} ({id})")

    def cmd_process_pre(self, trace, options, scripts):
        self.message(f"TestPlugin: Test pre 'process': {trace} {options} -- {scripts}")
        return True

    def cmd_process_post(self, trace, options, scripts, success):
        self.message(
            f"TestPlugin: Test post 'process': {trace} {options} -- {scripts} -> {success}"
        )
