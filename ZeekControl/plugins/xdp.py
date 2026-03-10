#
# A simple example plugin implementing a command "ps.zeek" that shows all Zeek
# processes currently running on any of the configured nodes, including  those
# not controlled by this zeekctl. The latter are marked with "(-)", while "our"
# processes get a "(+)".

import subprocess

import ZeekControl.cmdresult
import ZeekControl.plugin


class XDPZeek(ZeekControl.plugin.Plugin):
    def __init__(self):
        super().__init__(apiversion=1)

    def name(self):
        return "xdp"

    def pluginVersion(self):
        return 1

    def init(self):
        # TODO: Should these be in nodeKeys? idk
        xdp_program = self.getGlobalOption("XDPProgram")
        xdp_pin_path = self.getGlobalOption("XDPPinPath")
        if not xdp_program:
            return False

        if not xdp_pin_path:
            # TODO: error here?
            return False

        return True

    def uniq_nodes(self, nodes):
        return {
            (node.host, node.interface): node for node in nodes if node.interface
        }.values()

    # Gets the interface without potential prefixes
    def get_interface(self, node):
        return node.interface.rpartition("::")[-1]

    def cmd_start_pre(self, nodes):
        # Load the XDP program on each unique interface
        cmds = {
            (
                node,
                " ".join(
                    [
                        "xdp-loader",
                        "load",
                        self.get_interface(node),
                        self.getGlobalOption("XDPProgram"),
                        "-p",
                        self.getGlobalOption("XDPPinPath"),
                    ]
                ),
            )
            for node in self.uniq_nodes(nodes)
        }

        for node, success, output in self.executeParallel(cmds):
            if success:
                self.debug(f"Loaded XDP program on {self.get_interface(node)}")
            else:
                # This is an issue
                self.error(f"Failed to load XDP program on {self.get_interface(node)}: {output}")

        return nodes

    def cmd_stop_post(self, nodes):
        # stop has different nodes
        nodes = [node[0] for node in nodes]

        # Unload the XDP program from each unique interface
        cmds = {
            (
                node,
                " ".join(
                    [
                        "xdp-loader",
                        "unload",
                        self.get_interface(node),
                        "--all", # TODO: Don't unload all!
                    ]
                ),
            )
            for node in self.uniq_nodes(nodes)
        }

        for node, success, output in self.executeParallel(cmds):
            if success:
                self.debug(f"Unloaded XDP program on {self.get_interface(node)}")
            else:
                # Debug since this may not be an issue
                self.debug(f"Failed to unload XDP program on {self.get_interface(node)}: {output}")

        return nodes
