import ZeekControl.config
import ZeekControl.plugin


class ClusterBackendZeroMQ(ZeekControl.plugin.Plugin):
    def __init__(self):
        super().__init__(apiversion=1)

    def name(self):
        return "cluster_backend_zeromq"

    def pluginVersion(self):
        return 1

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
