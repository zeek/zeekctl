# Zeekctl test plugin that defines a string to write to zeekctl-config.zeek

import ZeekControl.plugin

class ZeekctlConfigTest(ZeekControl.plugin.Plugin):
    def __init__(self):
        super(ZeekctlConfigTest, self).__init__(apiversion=1)

    def name(self):
        return "zeekctlconfigtest"

    def pluginVersion(self):
        return 1

    def init(self):
        return True

    def zeekctl_config(self):
        return 'redef TestVar = "this is a test";\nredef Test="another test";'
