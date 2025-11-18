import ZeekControl.config
import ZeekControl.plugin


class ClusterBackendZeroMQ(ZeekControl.plugin.Plugin):
    def __init__(self):
        super().__init__(apiversion=1)

    def name(self):
        return "cluster_backend_zeromq"

    def pluginVersion(self):
        return 1

    def options(self):
        return [
            (
                "disable_unencrypted_warning",
                "bool",
                False,
                "Disable the multi-node unencrypted warning.",
            )
        ]

    def init(self):
        """
        Enable the plugin if ClusterBackend setting is ZeroMQ.
        """
        backend = self.getGlobalOption("ClusterBackend")
        if backend.lower() != "zeromq":
            return False

        # Switch topic separator for node topics to "." as that's what
        # the ZeroMQ cluster backend uses.
        if not self.getGlobalOption("ClusterTopicSeparator"):
            ZeekControl.config.Config.set_option("ClusterTopicSeparator", ".")

        # Lookup ZeekPort from the config and increment it by two. Use these two
        # ports to configure the XPUB/XSUB proxy component. The magic Port class
        # is located over in install.py
        base_port = ZeekControl.config.Config.get_option("ZeekPort")
        self.xpub_port = base_port
        self.xsub_port = base_port + 1
        ZeekControl.config.Config.set_option("ZeekPort", base_port + 2)

        # The manager address is used for listening of the XPUB/XSUB proxy.
        self.xpub_xsub_addr = ZeekControl.config.Config.manager().addr

        # Check if this is a multi-node cluster (multiple IP addresses) and
        # tell the user about it.
        addrs = {n.addr for n in self.nodes()}
        if len(addrs) > 1 and not self.getOption("disable_unencrypted_warning"):
            self.message(
                f'Warning: ZeroMQ cluster backend enabled and multi-node cluster detected (IPs {", ".join(addrs)}).'
            )
            self.message(
                "Communication between Zeek nodes using ZeroMQ is currently unencrypted. Use Broker with TLS if this"
            )
            self.message(
                "is concerning to you. ZeroMQ encryption is tracked at https://github.com/zeek/zeek/issues/4432"
            )
            self.message(
                "\nYou may disable this warning by setting the following option in zeekctl.cfg:"
            )
            self.message(
                "\n    cluster_backend_zeromq.disable_unencrypted_warning = 1\n"
            )

        return True

    def zeekctl_config(self):
        """
        Zeek 7.1 and later ship the following policy script to enable ZeroMQ.
        """
        script = "\n".join(
            [
                "# Enable ZeroMQ - the zeromq/connect script was deprecated with 8.1",
                '@if ( Version::at_least("8.1.0") )',
                "@load policy/frameworks/cluster/backend/zeromq",
                "@else",
                "@load policy/frameworks/cluster/backend/zeromq/connect",
                "@endif",
                "",
                f'redef Cluster::Backend::ZeroMQ::listen_xpub_endpoint = "tcp://{self.xpub_xsub_addr}:{self.xpub_port}";',
                f'redef Cluster::Backend::ZeroMQ::listen_xsub_endpoint = "tcp://{self.xpub_xsub_addr}:{self.xsub_port}";',
                f'redef Cluster::Backend::ZeroMQ::connect_xpub_endpoint = "tcp://{self.xpub_xsub_addr}:{self.xsub_port}";',
                f'redef Cluster::Backend::ZeroMQ::connect_xsub_endpoint = "tcp://{self.xpub_xsub_addr}:{self.xpub_port}";',
                "",
            ]
        )

        # Usually this runs automatically on the manager, but Zeectl supports
        # standalone mode and the node doesn't know it should run the proxy
        # thread for WebSocket functionality.
        if ZeekControl.config.Config.standalone:
            script += "\n".join(
                [
                    "",
                    "# Standalone: Run the XPUB/XSUB thread in standalone mode",
                    "redef Cluster::Backend::ZeroMQ::run_proxy_thread = T;",
                    "",
                    "# Standalone: Subscribe to zeek.cluster.node.zeek.",
                    "#             for controllee WebSocket interactions.",
                    "event zeek_init()",
                    "	{",
                    '	Cluster::subscribe("zeek.cluster.node.zeek.");',
                    "	}",
                ]
            )

        return script
