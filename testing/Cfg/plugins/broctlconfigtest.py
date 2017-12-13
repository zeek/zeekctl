# Broctl test plugin that defines a string to write to broctl-config.bro

import BroControl.plugin

class BroctlConfigTest(BroControl.plugin.Plugin):
    def __init__(self):
        super(BroctlConfigTest, self).__init__(apiversion=1)

    def name(self):
        return "broctlconfigtest"

    def pluginVersion(self):
        return 1

    def init(self):
        return True

    def broctl_config(self):
        return 'redef TestVar = "this is a test";\nredef Test="another test";'
