
# run all tools with an environment variable.
#    if config.Config.pfringclusterid != "0":
#        env += " PCAP_PF_RING_USE_CLUSTER_PER_FLOW=1 PCAP_PF_RING_CLUSTER_ID=%s" % config.Config.pfringclusterid

#
# A simple example plugin implementing a command "ps.bro" that shows all Bro
# processes currently running on any of the configured nodes, including  those
# not controlled by this broctl. The latter are marked with "(-)", while "our"
# processes get a "(+)".

import BroControl.plugin

class LBPFRing(BroControl.plugin.Plugin):
    def __init__(self):
        super(LBPFRing, self).__init__(apiversion=1)

    def name(self):
        return "lb_pf_ring"

    def pluginVersion(self):
        return 1

    def cmd_install_pre(self):
        self.nodes