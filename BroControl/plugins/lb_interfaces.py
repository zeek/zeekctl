
# Give a list of interfaces to run Bro processes on.

import BroControl.plugin

class LBInterfaces(BroControl.plugin.Plugin):
    def __init__(self):
        super(LBInterfaces, self).__init__(apiversion=1)

    def name(self):
        return "lb_interfaces"

    def pluginVersion(self):
        return 1

