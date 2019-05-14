# This plugin sets necessary environment variables to run Zeek with
# PF_RING load balancing.

import ZeekControl.plugin
import ZeekControl.config

class LBPFRing(ZeekControl.plugin.Plugin):
    def __init__(self):
        super(LBPFRing, self).__init__(apiversion=1)

    def name(self):
        return "lb_pf_ring"

    def pluginVersion(self):
        return 1

    def init(self):
        cluster_id = ZeekControl.config.Config.pfringclusterid
        if cluster_id == 0:
            return False

        pfringtype = ZeekControl.config.Config.pfringclustertype
        if pfringtype not in ("2-tuple", "4-tuple", "5-tuple", "tcp-5-tuple",
            "6-tuple", "round-robin"):
            self.error("Invalid configuration: PFRINGClusterType=%s" % pfringtype)
            return False

        # If the cluster type is not round-robin, then choose the corresponding
        # environment variable.
        pftype = ""
        if pfringtype != "round-robin":
            pftype = "PCAP_PF_RING_USE_CLUSTER_PER_FLOW"
            if pfringtype != "6-tuple":
                pftype += "_" + pfringtype.upper().replace("-", "_")

        useplugin = False
        first_app_instance = ZeekControl.config.Config.pfringfirstappinstance
        app_instance = first_app_instance

        dd = {}
        for nn in self.nodes():
            if nn.type != "worker" or nn.lb_method != "pf_ring":
                continue

            useplugin = True

            if nn.host in dd:
                if nn.interface not in dd[nn.host]:
                    app_instance = first_app_instance
                    dd[nn.host][nn.interface] = cluster_id + len(dd[nn.host])
            else:
                app_instance = first_app_instance
                dd[nn.host] = {nn.interface: cluster_id}

            # Apply environment variables, but do not override values from
            # the node.cfg or zeekctl.cfg files.
            if pftype:
                nn.env_vars.setdefault(pftype, "1")

            if nn.interface.startswith("zc:"):
                # For the case where a user is doing RSS with ZC or
                # load-balancing with zbalance_ipc (through libpcap over
                # pf_ring)
                nn.env_vars.setdefault("PCAP_PF_RING_ZC_RSS", "1")
                nn.interface = "%s@%d" % (nn.interface, app_instance)

            elif nn.interface.startswith("pf_ring::zc:"):
                # For the case where a user is doing RSS with ZC or
                # load-balancing with zbalance_ipc (through the zeek::pf_ring
                # plugin)
                nn.env_vars.setdefault("PCAP_PF_RING_ZC_RSS", "1")
                nn.interface = "%s@%d" % (nn.interface, app_instance)

            elif nn.interface.startswith("dnacl"):
                # For the case where a user is running pfdnacluster_master (deprecated)
                nn.interface = "%s@%d" % (nn.interface, app_instance)

            elif nn.interface.startswith("dna"):
                # For the case where a user is doing symmetric RSS with DNA (deprecated)
                nn.env_vars.setdefault("PCAP_PF_RING_DNA_RSS", "1")
                nn.interface = "%s@%d" % (nn.interface, app_instance)

            else:
                nn.env_vars.setdefault("PCAP_PF_RING_CLUSTER_ID", dd[nn.host][nn.interface])

            app_instance += 1
            nn.env_vars.setdefault("PCAP_PF_RING_APPNAME", "zeek-%s" % nn.interface)

        return useplugin

