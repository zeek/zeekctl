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

        pfringtype = BroControl.config.Config.pfringclustertype
        if pfringtype not in ("2-tuple", "4-tuple", "5-tuple", "tcp-5-tuple",
            "6-tuple", "round-robin"):
            self.error("Invalid configuration: PFRINGClusterType=%s" % pfringtype)

        # If the cluster type is not round-robin, then choose the corresponding
        # environment variable.
        pftype = ""
        if pfringtype != "round-robin":
            pftype = "PCAP_PF_RING_USE_CLUSTER_PER_FLOW"
            if pfringtype != "6-tuple":
                pftype += "_" + pfringtype.upper().replace("-", "_")

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
            if pftype:
                nn.env_vars.setdefault(pftype, "1")

            nn.env_vars.setdefault("PCAP_PF_RING_CLUSTER_ID", dd[nn.host][nn.interface])

        return True

