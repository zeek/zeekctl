import ZeekControl.config
import ZeekControl.plugin


class ClusterBackendCheck(ZeekControl.plugin.Plugin):
    def __init__(self):
        super().__init__(apiversion=1)

    def name(self):
        return "cluster_backend_check"

    def pluginVersion(self):
        return 1

    def init(self):
        return True

    def cmd_install_pre(self):
        """
        Ensure that the internal ClusterTopicSeparator is set. If it isn't,
        then the selected ClusterBackend plugin doesn't work right.
        """
        backend = self.getGlobalOption("ClusterBackend")
        topic_sep = self.getGlobalOption("ClusterTopicSeparator")

        if not topic_sep or len(topic_sep) == 0:
            self.error(
                f"internal ClusterTopicSeparator '{topic_sep}' invalid - is cluster backend '{backend}' working properly?"
            )
            return False

        return True
