# This plugin introduces a new load balancing method "custom", which does
# nothing by default.  To support packet source plugins, it allows to set a
# prefix and suffix for the interface name.  For example, add the following
# line to zeekctl.cfg to enable the AF_PACKET plugin:
# lb_custom.InterfacePrefix = af_packet::

import ZeekControl.plugin

class LBCustom(ZeekControl.plugin.Plugin):
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

            prefix = self.getOption("InterfacePrefix")
            suffix = self.getOption("InterfaceSuffix")
            nn.interface = "%s%s%s" % (prefix, nn.interface, suffix)

        return useplugin

    def options(self):
        custom_options = [
          ("InterfacePrefix", "string", "", "Prefix to prepend to the configured interface name."),
          ("InterfaceSuffix", "string", "", "Suffix to append to the configured interface name."),
        ]
        return custom_options
