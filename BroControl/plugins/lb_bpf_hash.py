
# Assign a number to each worker which is the mod value
# Add the restrict_filter to each of the auto-workers.

import BroControl.plugin

class LBBPFHash(BroControl.plugin.Plugin):
    def __init__(self):
        super(LBBPFHash, self).__init__(apiversion=1)

    def name(self):
        return "lb_bpf_hash"

    def pluginVersion(self):
        return 1

