# Zeekctl test plugin that defines custom node keys.

import ZeekControl.plugin


class NodeKeysTest(ZeekControl.plugin.Plugin):
    def __init__(self):
        super().__init__(apiversion=1)

    def name(self):
        return "nodekeystest"

    def pluginVersion(self):
        return 1

    def init(self):
        with open("keys.out", "w") as f:
            for n in self.nodes():
                f.write(f"key1: {n.nodekeystest_key1}\n")
                f.write(f"key2: {n.nodekeystest_key2}\n")

        return True

    def nodeKeys(self):
        return ["key1", "key2"]
