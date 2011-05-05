#
# Registry managing plugins.

import sys
import os

import util
import config
import node

class PluginRegistry:
    def __init__(self):
        self._plugins = []
        self._dirs = []
        self._cmds = {}

    def addDir(self, dir):
        """Adds a directory to search for plugins."""
        self._dirs += [dir]

    def loadPlugins(self):
        """Loads all plugins found in any of the added directories."""
        self._loadPlugins()

        # Init options.
        for plugin in self._plugins:
            plugin._registerOptions()

            for (cmd, args, descr) in plugin.commands():
                self._cmds["%s.%s" % (plugin.prefix(), cmd)] = (plugin, args, descr)

    def initPlugins(self):
        """Initialized all loaded plugins."""
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
                new_nodes = p.__class__.__dict__[method](p, nodes, *args)

                if new_nodes != None:
                    nodes = new_nodes

            except LookupError:
                pass

        return nodes

    def cmdPre(self, cmd, *args):
        """Executes the ``cmd_<XXX>_pre`` function for a command *not* taking
        a list of nodes as its first argument. All arguments are passed on.
        Returns the True if all plugins returned True.
        """
        method = "cmd_%s_pre" % cmd

        for p in self._plugins:
            try:
                p.__class__.__dict__[method](p, *args)
            except LookupError:
                pass

    def cmdPostWithNodes(self, cmd, nodes, *args):
        """Executes the ``cmd_<XXX>_post`` function for a command taking a list
        of nodes as its first argument. All other arguments are passed on.
        """
        method = "cmd_%s_post" % cmd

        for p in self._plugins:
            try:
                p.__class__.__dict__[method](p, nodes, *args)
            except LookupError:
                pass

    def cmdPostWithResults(self, cmd, results, *args):
        """Executes the ``cmd_<XXX>_post`` function for a command taking a
        list of tuples ``(node, bool)`` as its first argument. All other
        arguments are passed on.
        """
        method = "cmd_%s_post" % cmd

        for p in self._plugins:
            try:
                p.__class__.__dict__[method](p, results, *args)
            except LookupError:
                pass

    def cmdPost(self, cmd, *args):
        """Executes the ``cmd_<XXX>_post`` function for a command *not* taking
        a list of nodes as its first argument. All arguments are passed on.
        Returns the True if all plugins returned True.
        """
        method = "cmd_%s_post" % cmd

        for p in self._plugins:
            try:
                p.__class__.__dict__[method](p, *args)
            except LookupError:
                pass

    def runCustomCommand(self, cmd, args):
        """Runs a custom command *cmd* a string *args* as argument. Returns
        False if no such command is known"""
        try:
            (plugin, usage, descr) = self._cmds[cmd]

            prefix = plugin.prefix()

            if cmd.startswith("%s." % prefix):
                cmd = cmd[len(prefix) + 1:]

            plugin.cmd_custom(cmd, args)
            return True

        except LookupError:
            return False

    def allCustomCommands(self):
        """Returns a list of string tuples *(cmd, descr)* listing all commands
        defined by any plugin."""

        cmds = []

        for cmd in sorted(self._cmds.keys()):
            (plugin, args, descr) = self._cmds[cmd]
            cmds += [(cmd, args, descr)]

        return cmds

    def addNodeKeys(self):
        """Adds all plugins' node keys to the list of supported keys in
        ``Node``.."""
        for p in self._plugins:
            for key in p.nodeKeys():
                key = "%s_%s" % (p.prefix(), key)
                p.debug("adding node key %s for plugin %s" % (key, p.name()))
                node.Node.addKey(key)

    def addAnalyses(self, analysis):
        """Adds all plugins' analyses specification to an ``Analysis``
        instace."""
        for p in self._plugins:
            for (name, descr, mechanism) in p.analyses():

                name = "%s.%s" % (p.prefix(), name)

                # Convert 2-tuple(s) to analysis.dat format.
                if not isinstance(mechanism, list):
                    mechanism = [mechanism]

                mechanism = ["%s:%s" % (m[0], m[1]) for m in mechanism]
                mechanism = ",".join(mechanism)

                p.debug("adding analysis %s for plugin %s (%s)" % (name, p.name(), mechanism))
                analysis.addAnalysis(name, mechanism, descr)

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

