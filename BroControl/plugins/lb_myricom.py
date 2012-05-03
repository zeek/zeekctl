
# run all external tools with an environment variable
# env += " SNF_NUM_RINGS=10 SNF_FLAGS=0x101"

import BroControl.plugin

class LBMyricom(BroControl.plugin.Plugin):
    def __init__(self):
        super(LBMyricom, self).__init__(apiversion=1)

    def name(self):
        return "lb_myricom"

    def pluginVersion(self):
        return 1

