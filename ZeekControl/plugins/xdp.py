from pathlib import Path

import ZeekControl.plugin


class XDPZeek(ZeekControl.plugin.Plugin):
    def __init__(self):
        super().__init__(apiversion=1)

    def name(self):
        return "xdp"

    def pluginVersion(self):
        return 1

    def makeLoadCommand(self, interface):
        return " ".join(
            [
                self.getOption("XDPLoader"),
                "--pin-path-prefix",
                self.getOption("PinPath"),
                "load",
                "--obj",
                self.getOption("Program"),
                "--iface",
                interface,
                "-m",
                self.getOption("AttachMode"),
                "--flow-map-max-size",
                str(self.getOption("FlowMapMaxSize")),
                "--ip-pair-map-max-size",
                str(self.getOption("IPPairMapMaxSize")),
            ]
        )

    def makeUnloadCommand(self, interface):
        return " ".join(
            [
                self.getOption("XDPLoader"),
                "--pin-path-prefix",
                self.getOption("PinPath"),
                "unload",
                "--iface",
                interface,
            ]
        )

    def options(self):
        plugin_dir = self.getGlobalOption("PluginZeekDir")
        default_path = Path(plugin_dir) / "xdp_shunt" / "bpf" / "filter.o"

        return [
            ("enabled", "bool", False, "Set to enable plugin"),
            ("Program", "string", str(default_path), "The XDP program"),
            ("PinPath", "string", "/sys/fs/bpf/zeek/", "The XDP pin path"),
            (
                "AttachMode",
                "string",
                "unspecified",
                "The XDP attach mode (native,skb,hw,unspecified)",
            ),
            (
                "FlowMapMaxSize",
                "int",
                65535,
                "Max number of shunted flows",
            ),
            (
                "IPPairMapMaxSize",
                "int",
                65535,
                "Max number of shunted IP pairs",
            ),
            (
                "XDPLoader",
                "string",
                "${BinDir}/zeek-xdp-loader",
                "The XDP loader",
            ),
        ]

    def init(self):
        if not self.getOption("enabled"):
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
            (node, self.makeLoadCommand(self.get_interface(node)))
            for node in self.uniq_nodes(nodes)
        }

        for node, success, output in self.executeParallel(cmds):
            if success:
                self.debug(f"Loaded XDP program on {self.get_interface(node)}")
            else:
                # This is an issue
                self.error(
                    f"Failed to load XDP program on {self.get_interface(node)}: {output}"
                )

        return nodes

    def cmd_stop_post(self, nodes):
        # stop has different nodes
        nodes = [node[0] for node in nodes]

        # Unload the XDP program from each unique interface
        cmds = {
            (node, self.makeUnloadCommand(self.get_interface(node)))
            for node in self.uniq_nodes(nodes)
        }

        for node, success, output in self.executeParallel(cmds):
            if success:
                self.debug(f"Unloaded XDP program on {self.get_interface(node)}")
            else:
                # Debug since this may not be an issue
                self.debug(
                    f"Failed to unload XDP program on {self.get_interface(node)}: {output}"
                )

        return nodes

    def zeekctl_config(self):
        # Since we assume that the program is loaded, no need to redef any options associated with
        # loading the XDP program (attach mode, map sizes, etc.)
        pin_path = self.getOption("PinPath")

        script = "\n".join(
            [
                "# Enable XDP",
                "@load frameworks/xdp-shunt",
                "",
                "# Set XDP pin path for maps",
                f'redef XDP::pin_path = "{pin_path}";',
                "",
            ]
        )

        return script
