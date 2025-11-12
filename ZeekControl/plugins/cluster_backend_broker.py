import ZeekControl.config
import ZeekControl.plugin


class ClusterBackendBroker(ZeekControl.plugin.Plugin):
    def __init__(self):
        super().__init__(apiversion=1)

    def name(self):
        return "cluster_backend_broker"

    def pluginVersion(self):
        return 1

    def init(self):
        """
        Enable the plugin if ClusterBackend setting is Broker.
        """
        backend = self.getGlobalOption("ClusterBackend")
        if backend.lower() != "broker":
            return False

        # Switch topic separator for node topics to "/".
        if not self.getGlobalOption("ClusterTopicSeparator"):
            ZeekControl.config.Config.set_option("ClusterTopicSeparator", "/")

        return True

    def zeekctl_config(self):
        """
        If the version of Zeek already has the broker policy scripts, load
        these, otherwise Broker is anyhow enabled by default.
        """
        script = "\n".join(
            [
                "# Load Broker's policy scripts if they exist.",
                '@if ( can_load("policy/frameworks/cluster/backend/broker") )',
                "@load policy/frameworks/cluster/backend/broker",
                "@endif",
            ]
        )

        return script
