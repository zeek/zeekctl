#
# A simple test plugin.
#

import BroControl.plugin

class TestPlugin(BroControl.plugin.Plugin):

    def name(self):
        return "TestPlugin"

    def prefix(self):
        return "test"

    def version(self):
        return 1

    def init(self):
        foo = self.getOption("foo")

        bar = self.getState("bar")
        if not bar:
            bar = "1"

        self.setState("bar", str(int(bar) + 1))

        self.message("Test initialized")
        self.message("The value of foo is: %s" % foo)
        self.message("The current value of bar is: %s" % bar)

    def options(self):
        return [("foo", "string", "1", "Just a test option.")]

    def commands(self):
        return [("bar", "A test command from the Test plugin.")]

    def cmd_check_pre(self, nodes):
        self.message("Test pre check: %s" % str(nodes))

    def cmd_check_post(self, nodes):
        self.message("Test post check: %s" % str(nodes))

    def cmd_custom(self, cmd, args):
        self.message("My command: %s" % args)
