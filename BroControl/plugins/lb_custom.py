# This plugin can be used for custom load balancing solutions.
# It allows to set prefix and suffix for the used interface.

import BroControl.plugin

class LBCustom(BroControl.plugin.Plugin):
    def __init__(self):
        super(LBCustom, self).__init__(apiversion=1)

    def name(self):
        return "lb_custom"

    def pluginVersion(self):
        return 1

    def init(self):
        useplugin = False

        for nn in self.nodes():
            if nn.type != "worker" or nn.lb_method != "custom":
                continue

            useplugin = True

            iface_prefix = self.getOption("InterfacePrefix")
            iface_suffix = self.getOption("InterfaceSuffix")
            nn.interface = "%s%s%s" % (iface_prefix, nn.interface, iface_suffix)

        return useplugin

    def options(self):
          custom_options = [
            ("InterfacePrefix", "string", "", "Prefix to prepend to the configured interface name."),
            ("InterfaceSuffix", "string", "", "Suffix to append to the configured interface name."),
          ]
          return custom_options
