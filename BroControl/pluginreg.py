#
# Registry managing plugins.

import sys
import os

import util
import config

class PluginRegistry:
    def __init__(self):
        self._plugins = []
        self._dirs = []
        self._cmds = {}

    def addDir(self, dir):
        """Adds a directory to search for plugins."""
        self._dirs += [dir]

    def initPlugins(self):
        """Loads all plugins found in any of the added directories and fully
        initialized them."""
        self._loadPlugins()

        # Init options.
        for plugin in self._plugins:
            plugin._registerOptions()

            for (cmd, descr) in plugin.commands():
                self._cmds["%s.%s" % (plugin.prefix(), cmd)] = (plugin, descr)

        plugins = []

        for p in self._plugins:
            if p.init():
                plugins += [p]

        self._plugins = plugins

    def finishPlugins(self):
        """Shuts all plugins down."""
        pass

    def cmdPreWithNodes(self, cmd, nodes, *args):
        """Executes the ``cmd_<XXX>_pre`` function for a command taking a list
        of nodes as its first argument. All other arguments are passed on.
        Returns the filtered node list as returned by the chain of all
        plugins."""

        method = "cmd_%s_pre" % cmd

        for p in self._plugins:
            try:
                nodes = p.__class__.__dict__[method](nodes, *args)
            except LookupError:
                pass

        return nodes

    def cmdPre(self, cmd, *args):
        """Executes the ``cmd_<XXX>_pre`` function for a command *not* taking
        a list of nodes as its first argument. All arguments are passed on.
        Returns the True if all plugins returned True."""
        pass

    def cmdPost(self, cmd, nodes, *args):
        """Executes the ``cmd_<XXX>_post`` function for a command. All
        arguments are passed on."""
        pass

    def runCustomCommand(self, cmd, args):
        """Runs a custom command *cmd* a string *args* as argument. Returns
        False if no such command is known"""
        try:
            (plugin, descr) = self._cmds[cmd]
            plugin.cmd_custom(cmd, args)
            return True

        except LookupError:
            return False

    def allCustomCommands(self):
        """Returns a list of string tuples *(cmd, descr)* listing all commands
        defined by any plugin."""

        cmds = []

        for cmd in sorted(self._cmds.keys()):
            (plugin, descr) = self._cmds[cmd]
            cmds += [(cmd, descr)]

        return cmds

    def _loadPlugins(self):

        sys.path.append(config.Config.libdirinternal)

        for path in self._dirs:
            for root, dirs, files in os.walk(os.path.abspath(path)):
                for name in files:
                    if name.endswith(".py") and not name.startswith("__"):
                        self._importPlugin(os.path.join(root, name[:-3]))

    def _importPlugin(self, path):
        sys.path = [os.path.dirname(path)] + sys.path

        try:
            module = __import__(os.path.basename(path))
        except Exception, e:
            util.error("cannot import plugin %s: %s" % (path, e))

        sys.path = sys.path[1:]

        found = False

        for cls in module.__dict__.values():
            try:
                if issubclass(cls, plugin.Plugin):
                    p = cls()
                    util.debug(1, "Loaded plugin %s from %s (version %d, prefix %s)"
                        % (p.name(), module.__file__, p.version(), p.prefix()))

                    self._plugins += [p]
                    found = True

            except TypeError:
                # cls is not a class.
                pass

        if not found:
            util.warn("no plugin found in %s" % module.__file__)


import plugin
