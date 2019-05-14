# Zeekctl test plugin that defines custom commands.

import ZeekControl.plugin

class CommandTest(ZeekControl.plugin.Plugin):
    def __init__(self):
        super(CommandTest, self).__init__(apiversion=1)

    def name(self):
        return "commandtest"

    def pluginVersion(self):
        return 1

    def init(self):
        return True

    def commands(self):
        return [("testcmd", "[<nodes>]", "Test command that expects arguments"),
                ("", "", "Another test command")]

    def cmd_custom(self, cmd, args, cmdout):
        results = ZeekControl.cmdresult.CmdResult()

        # This is an easy way to force the plugin command to return failure.
        if args == "fail":
            results.ok = False
        else:
            results.ok = True

        cmdout.info("Command name: %s" % cmd)
        cmdout.info("Command args: %s" % args)

        return results
