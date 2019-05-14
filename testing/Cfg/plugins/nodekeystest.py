# Zeekctl test plugin that defines custom node keys.

import ZeekControl.plugin

class NodeKeysTest(ZeekControl.plugin.Plugin):
    def __init__(self):
        super(NodeKeysTest, self).__init__(apiversion=1)

    def name(self):
        return "nodekeystest"

    def pluginVersion(self):
        return 1

    def init(self):
        with open("keys.out", "w") as f:
            for n in self.nodes():
                f.write("key1: %s\n" % n.nodekeystest_key1)
                f.write("key2: %s\n" % n.nodekeystest_key2)

        return True

    def nodeKeys(self):
        return ["key1", "key2"]
