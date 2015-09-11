# This plugin creates and loads the necessary configuration to run Bro using
# AF_PACKET's load balancing via PACKET_FANOUT.

import os

import BroControl.plugin
import BroControl.config

class LBPacketFanout(BroControl.plugin.Plugin):
    def __init__(self):
        super(LBPacketFanout, self).__init__(apiversion=1)


    def name(self):
        return "lb_packet_fanout"


    def pluginVersion(self):
        return 1


    def init(self):
        fanout_id = BroControl.config.Config.packetfanoutid
        if not (0 <= fanout_id < 65536):
            return False

        for nn in self.nodes():
            if nn.type == "worker" and nn.lb_method == "packet_fanout":
                # Enable packet fanout
                BroControl.config.Config.packetfanoutenable = True
                return True

        return False

