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
        pfringid = int(BroControl.config.Config.pfringclusterid)
        if pfringid == 0:
            return True

        dd = {}
        for nn in self.nodes():
            if nn.type != "worker" or nn.lb_method != "pf_ring":
                continue

            if nn.host in dd:
                if nn.interface not in dd[nn.host]:
                    dd[nn.host][nn.interface] = pfringid + len(dd[nn.host])
            else:
                dd[nn.host] = { nn.interface : pfringid }

            # Apply environment variables, but do not override values from
            # the node.cfg or broctl.cfg files.
            nn.env_vars.setdefault("PCAP_PF_RING_USE_CLUSTER_PER_FLOW", "1")
            nn.env_vars.setdefault("PCAP_PF_RING_CLUSTER_ID", dd[nn.host][nn.interface])

        return True

