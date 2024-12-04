# Zeekctl test plugin that defines custom commands using the old BroControl
# legacy API.

import BroControl.cmdresult
import BroControl.plugin


class CommandTest(BroControl.plugin.Plugin):
    def __init__(self):
        super().__init__(apiversion=1)

    def name(self):
        return "commandtest"

    def pluginVersion(self):
        return 1

    def init(self):
        return True

    def commands(self):
        return [
            ("testcmd", "[<nodes>]", "Test command that expects arguments"),
            ("", "", "Another test command"),
        ]

    def cmd_custom(self, cmd, args, cmdout):
        results = BroControl.cmdresult.CmdResult()

        # This is an easy way to force the plugin command to return failure.
        if args == "fail":
            results.ok = False
        else:
            results.ok = True

        cmdout.info(f"Command name: {cmd}")
        cmdout.info(f"Command args: {args}")

        return results
