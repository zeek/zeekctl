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

    def cmd_start_pre(self, nodes):
        # Load the XDP program on each interface
        interfaces = {node.interface.rpartition('::')[-1] for node in nodes if node.interface};
        for interface in interfaces:
            cmd = [
                "xdp-loader",
                "load",
                interface,
                self.getGlobalOption("XDPProgram"),
                "-p",
                self.getGlobalOption("XDPPinPath"),
            ]

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"Kernel rejected the program on {interface}: {res.stderr}")
                continue

        return nodes

    def cmd_stop_post(self, nodes):
        # Unload the XDP program on each interface
        interfaces = {node[0].interface.rpartition('::')[-1] for node in nodes if node[0].interface};
        for interface in interfaces:
            cmd = [
                "xdp-loader",
                "unload",
                interface,
                "--all", # TODO: Don't unload all!
            ]

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"Kernel could not unload programs on {interface}: {res.stderr}")
                continue

        return nodes
