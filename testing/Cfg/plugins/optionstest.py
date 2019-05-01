# Zeekctl test plugin that defines plugin options.

import ZeekControl.plugin

class OptionsTest(ZeekControl.plugin.Plugin):
    def __init__(self):
        super(OptionsTest, self).__init__(apiversion=1)

    def name(self):
        return "optionstest"

    def pluginVersion(self):
        return 1

    def init(self):
        with open("options.out", "w") as f:
            f.write("%s\n" % self.getOption("opt1"))
            f.write("%s\n" % self.getOption("opt2"))
            f.write("%s\n" % self.getOption("opt3"))

        return True

    def options(self):
        return [("opt1", "bool", True, "Boolean option"),
                ("opt2", "string", "test str", "String option"),
                ("opt3", "int", 42, "Int option")]
