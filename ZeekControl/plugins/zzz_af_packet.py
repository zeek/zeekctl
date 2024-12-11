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
        return ["fanout_id", "fanout_mode", "buffer_size"]

    def zeekctl_config(self):
        script = ""

        # Add custom configuration values per worker.
        for nn in self.nodes():
            if nn.type != "worker" or not nn.lb_procs:
                continue

            params = ""

            if nn.af_packet_fanout_id:
                params += f"\n  redef AF_Packet::fanout_id = {nn.af_packet_fanout_id};"
            if nn.af_packet_fanout_mode:
                params += (
                    f"\n  redef AF_Packet::fanout_mode = {nn.af_packet_fanout_mode};"
                )
            if nn.af_packet_buffer_size:
                params += (
                    f"\n  redef AF_Packet::buffer_size = {nn.af_packet_buffer_size};"
                )

            if params:
                script += f'\n@if( peer_description == "{nn.name}" ) {params}\n@endif'

        return script
