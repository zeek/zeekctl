# This plugin sets necessary environment variables to run Bro with
# PF_RING load balancing.

import BroControl.plugin
import BroControl.config

class LBPFRing(BroControl.plugin.Plugin):
    def __init__(self):
        super(LBPFRing, self).__init__(apiversion=1)

    def name(self):
        return "lb_pf_ring"

    def pluginVersion(self):
        return 1

    def init(self):
        for nn in self.nodes():
            if nn.type != "worker":
                continue

            if nn.lb_method == "pf_ring":
                if BroControl.config.Config.pfringclusterid != "0":
                    nn.env_vars += ["PCAP_PF_RING_USE_CLUSTER_PER_FLOW=1"]
                    nn.env_vars += ["PCAP_PF_RING_CLUSTER_ID=%s" % BroControl.config.Config.pfringclusterid]
