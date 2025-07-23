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
                "# Enable ZeroMQ",
                "@load policy/frameworks/cluster/backend/zeromq/connect",
            ]
        )

        return script
