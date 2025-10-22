import ZeekControl.plugin


class AF_Packet(ZeekControl.plugin.Plugin):
    def __init__(self):
        super().__init__(apiversion=1)

    def name(self):
        return "af_packet"

    def pluginVersion(self):
        return 1

    def init(self):
        """
        Only use the plugin if there is a worker using AF_PACKET for load balancing.

        There are two ways to recognize AF_PACKET usage:
          * The specified interface already starts with af_packet:: (lb_custom
            or interfaces usage).
          * lb_method is set to "af_packet" in which case the interface
            is prefixed with af_packet:: by this plugin.
        """
        result = False
        for nn in self.nodes():
            if nn.type != "worker" or not nn.lb_procs:
                continue

            if nn.interface.startswith("af_packet::"):
                result = True

            if nn.lb_method == "af_packet":
                if nn.interface.startswith("af_packet::"):
                    self.error(
                        f"unexpected af_packet:: prefix for interface {nn.interface} of {nn}"
                    )
                    return False

                nn.interface = f"af_packet::{nn.interface}"
                result = True

        return result

    def nodeKeys(self):
        return [
            "block_size",
            "block_timeout",
            "buffer_size",
            "checksum_validation_mode",
            "enable_defrag",
            "enable_fanout",
            "enable_hw_timestamping",
            "fanout_id",
            "fanout_mode",
            "link_type",
        ]

    def zeekctl_config(self):
        script = ""

        # Add custom configuration values per worker.
        for nn in self.nodes():
            if nn.type != "worker" or not nn.lb_procs:
                continue

            params = ""

            for key in self.nodeKeys():
                prefixed_key = f"{self.prefix()}_{key}"
                v = getattr(nn, prefixed_key, None)
                if v and v.strip():
                    params += f"\n  redef AF_Packet::{key} = {v};"

            if params:
                script += f'\n@if( peer_description == "{nn.name}" ) {params}\n@endif'

        return script
