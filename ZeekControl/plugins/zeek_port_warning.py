"""
A plugin warning about the ZeekPort change coming with Zeek 5.2.
"""
import textwrap

import ZeekControl.plugin
import ZeekControl.cmdresult



class ZeekPortWarningPlugin(ZeekControl.plugin.Plugin):
    def __init__(self):
        super(ZeekPortWarningPlugin, self).__init__(apiversion=1)

    def name(self):
        return "ZeekPort warning"

    def prefix(self):
        return "zeek_port_warning"

    def pluginVersion(self):
        return 1

    def options(self):
        return [("disable", "bool", False, "Disable the ZeekPort warning.")]

    def warning_banner(self, text):
        for i, line in enumerate(text.splitlines()):
            if i == 0 and not line:
                continue
            self.message("WARNING: " + line)

    def init(self):
        """
        Print a warning about the change of the ZeekPort option.

        We're just assuming that if it's 47760, the default was selected.
        """
        if self.getOption("disable"):
            return

        zeek_port = self.getGlobalOption("ZeekPort")
        uses_old_default_port = (zeek_port == 47760)

        if uses_old_default_port:
            self.warning_banner("*" * 80)
            if self.getGlobalOption("os") == "Linux":
                self.warning_banner(textwrap.dedent(
                    """
                    You're using Linux with the default ZeekPort setting 47760. This configuration
                    is know to cause persistent worker failures with error messages as follows:

                        error in <...>/cluster/setup-connections.zeek, lines 94-96: Failed to listen on INADDR_ANY:47764 (...)

                    """))

            self.warning_banner(textwrap.dedent("""
                Starting with Zeek 5.2, the default ZeekPort used by zeekctl will
                change from 47760 to 27760 in order to avoid potential port collisions
                with other processes due to 47760 falling right into Linux's default
                ephemeral port range.

                Consider changing the ZeekPort option in your zeekctl.cfg to 27760
                now to prepare for this change. Doing so will silence this warning.

                    ZeekPort = 27760

                Note, if you're employing strict firewall rules between Zeek nodes,
                you'll likely need to update these rules. If you're using Zeek on
                a single physical host, no further action should be required.
                If possible do test the change in a non-production environment.

                To silence this warning without changing the ZeekPort option,
                set zeek_port_warning.disable = 1 in zeekctl.cfg.

                See the following PR for more details:
                    https://github.com/zeek/zeekctl/pull/41

                Feel free to reach out on zeekorg.slack.com or community.zeek.org if
                you have any questions around this change.
            """))

            self.warning_banner("*" * 80)
