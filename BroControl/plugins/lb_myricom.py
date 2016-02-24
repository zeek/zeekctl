# This plugin sets necessary environment variables to run Bro with
# myricom load balancing.

import BroControl.plugin

class LBMyricom(BroControl.plugin.Plugin):
    def __init__(self):
        super(LBMyricom, self).__init__(apiversion=1)

    def name(self):
        return "lb_myricom"

    def pluginVersion(self):
        return 1

    def init(self):
        useplugin = False

        for nn in self.nodes():
            if nn.type != "worker" or nn.lb_method != "myricom":
                continue

            useplugin = True

            # Apply environment variables, but do not override values from
            # the node.cfg or broctl.cfg files.
            nn.env_vars.setdefault("SNF_NUM_RINGS", nn.lb_procs)
            nn.env_vars.setdefault("SNF_FLAGS", "0x101")

        return useplugin

