
# Give a list of mac addresses that traffic is balanced across.
# Run processes for each MAC address 

import BroControl.plugin

class LBBPFMAC(BroControl.plugin.Plugin):
    def __init__(self):
        super(LBBPFMAC, self).__init__(apiversion=1)

    def name(self):
        return "lb_bpf_mac"

    def pluginVersion(self):
        return 1

