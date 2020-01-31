#
# Registry managing plugins.

import sys
import os
import logging

from ZeekControl import cmdresult
from ZeekControl import node
from ZeekControl import plugin

# Note, when changing this, also adapt doc string for Plugin.__init__.
_CurrentAPIVersion = 1

class PluginRegistry:
    def __init__(self):
        self._plugins = []
        self._dirs = []
        self._cmds = {}

    def _activeplugins(self):
        return filter(lambda p: p.activated, self._plugins)

    def addDir(self, dir):
        """Adds a directory to search for plugins."""
        if dir not in self._dirs:
            self._dirs += [dir]

    def loadPlugins(self, cmdout, executor):
        """Loads all plugins found in any of the added directories."""
        self._loadPlugins(cmdout)

        for p in self._plugins:
            p.executor = executor

    def initPluginOptions(self):
        """Initialize options for all loaded plugins."""
        for p in self._plugins:
            p._registerOptions()

    def initPlugins(self, cmdout):
        """Initialize all loaded plugins."""
        for p in self._plugins:
            p.activated = False

            try:
                init = p.init()
            except Exception as err:
                cmdout.warn("Plugin '%s' not activated because its init() method raised exception: %s" % (p.name(), err))
                continue

            if not init:
                logging.debug("Plugin '%s' not activated because its init() returned False", p.name())
                continue

            p.activated = True

    def initPluginCmds(self):
        """Initialize commands provided by all activated plugins."""
        self._cmds = {}
        for p in self._activeplugins():
            for (cmd, args, descr) in p.commands():
                full_cmd = "%s.%s" % (p.prefix(), cmd) if cmd else p.prefix()
                self._cmds[full_cmd] = (p, args, descr)

    def finishPlugins(self):
        """Shuts all plugins down."""
        for p in self._activeplugins():
            p.done()

    def hostStatusChanged(self, host, status):
        """Calls all plugins Plugin.hostStatusChanged_ methods; see there for
        parameter semantics."""
        for p in self._activeplugins():
            p.hostStatusChanged(host, status)

    def zeekProcessDied(self, node):
        """Calls all plugins Plugin.zeekProcessDied_ methods; see there for
        parameter semantics."""
        for p in self._activeplugins():
            p.zeekProcessDied(node)
             # TODO: Can we recognize when this is in use to warn about deprecation?
            p.broProcessDied(node)

    def cmdPreWithNodes(self, cmd, nodes, *args):
        """Executes the ``cmd_<XXX>_pre`` function for a command taking a list
        of nodes as its first argument. All other arguments are passed on.
        Returns the filtered node list as returned by the chain of all
        plugins."""

        method = "cmd_%s_pre" % cmd

        for p in self._activeplugins():
            func = getattr(p, method)
            new_nodes = func(nodes, *args)
            if new_nodes is not None:
                nodes = new_nodes

        return nodes

    def cmdPre(self, cmd, *args):
        """Executes the ``cmd_<XXX>_pre`` function for a command *not* taking
        a list of nodes as its first argument. All arguments are passed on.
        Returns True if no plugins returned False.
        """
        method = "cmd_%s_pre" % cmd
        result = True

        for p in self._activeplugins():
            func = getattr(p, method)
            if func(*args) == False:
                result = False

        return result

    def cmdPostWithNodes(self, cmd, nodes, *args):
        """Executes the ``cmd_<XXX>_post`` function for a command taking a list
        of nodes as its first argument. All other arguments are passed on.
        """
        method = "cmd_%s_post" % cmd

        for p in self._activeplugins():
            func = getattr(p, method)
            func(nodes, *args)

    def cmdPostWithResults(self, cmd, results, *args):
        """Executes the ``cmd_<XXX>_post`` function for a command taking a
        list of tuples ``(node, bool)`` as its first argument. All other
        arguments are passed on.
        """
        method = "cmd_%s_post" % cmd

        for p in self._activeplugins():
            func = getattr(p, method)
            func(results, *args)

    def cmdPost(self, cmd, *args):
        """Executes the ``cmd_<XXX>_post`` function for a command *not* taking
        a list of nodes as its first argument. All arguments are passed on.
        """
        method = "cmd_%s_post" % cmd

        for p in self._activeplugins():
            func = getattr(p, method)
            func(*args)

    def runCustomCommand(self, cmd, args, cmdout):
        """Runs a custom command *cmd* with string *args* as argument. Returns
        a CmdResult object which contains the command results."""

        try:
            myplugin, usage, descr = self._cmds[cmd]
        except LookupError:
            return cmdresult.CmdResult(ok=False, unknowncmd=True)

        prefix = myplugin.prefix()

        if cmd.startswith("%s." % prefix):
            cmd = cmd[len(prefix)+1:]

        return myplugin.cmd_custom(cmd, args, cmdout)

    def getZeekctlConfig(self, cmdout):
        """Call the zeekctl_config method on all plugins in case a plugin
        needs to add some custom script code to the zeekctl-config.zeek file.
        Returns a string containing Zeek script code from the plugins.
        """

        extra_code = []

        for p in self._activeplugins():
            if p.broctl_config():
                cmdout.error("Plugin '%s' uses discontinued method 'broctl_config'; use 'zeekctl_config' instead" % p.name())

            code = p.zeekctl_config()
            if code:
                # Make sure first character of returned string is a newline
                extra_code.append("")
                extra_code.append("# Begin code from %s plugin" % p.name())
                extra_code.append(code)
                extra_code.append("# End code from %s plugin" % p.name())

        if extra_code:
            # Make sure last character of returned string is a newline
            extra_code.append("")

        return "\n".join(extra_code)

    def allCustomCommands(self):
        """Returns a list of string tuples *(cmd, args, descr)* listing all
        commands defined by any plugin."""

        cmds = []

        for cmd in sorted(self._cmds.keys()):
            _, args, descr = self._cmds[cmd]
            cmds += [(cmd, args, descr)]

        return cmds

    def addNodeKeys(self):
        """Adds all plugins' node keys to the list of supported keys in
        ``Node``."""

        for p in self._plugins:
            for key in p.nodeKeys():
                key = "%s_%s" % (p.prefix(), key)
                logging.debug("adding node key %s for plugin %s", key, p.name())
                node.Node.addKey(key)

    def _loadPlugins(self, cmdout):
        # Don't visit the same dir twice (this also prevents infinite
        # recursion when following symlinks).
        visited_dirs = set()

        for path in self._dirs:

            for root, dirs, files in os.walk(os.path.abspath(path),
                                             followlinks=True):
                stat = os.stat(root)
                visited_dirs.add((stat.st_dev, stat.st_ino))
                dirs_to_visit_next = []

                for dir in dirs:
                    stat = os.stat(os.path.join(root, dir))

                    if (stat.st_dev, stat.st_ino) not in visited_dirs:
                        dirs_to_visit_next.append(dir)

                dirs[:] = dirs_to_visit_next

                for name in files:
                    if name.endswith(".py") and not name.startswith("__"):
                        self._importPlugin(os.path.join(root, name[:-3]), cmdout)

    def _importPlugin(self, path, cmdout):
        sys.path = [os.path.dirname(path)] + sys.path

        try:
            module = __import__(os.path.basename(path))
        except Exception as e:
            cmdout.warn("cannot import plugin %s: %s" % (path, e))
            return
        finally:
            sys.path = sys.path[1:]

        found = False

        for cls in module.__dict__.values():
            try:
                is_plugin = issubclass(cls, plugin.Plugin)
            except TypeError:
                # cls is not a class.
                continue

            if is_plugin:
                found = True

                try:
                    p = cls()
                except Exception as e:
                    cmdout.warn("plugin class %s __init__ failed: %s" % (cls.__name__, e))
                    break

                # verify that the plugin overrides all required methods
                try:
                    logging.debug("Found plugin %s from %s (version %d, prefix %s)",
                               p.name(), module.__file__, p.pluginVersion(), p.prefix())
                except NotImplementedError:
                    cmdout.warn("failed to load plugin at %s because it doesn't override required methods" % path)
                    continue

                if p.apiVersion() != _CurrentAPIVersion:
                    cmdout.warn("failed to load plugin %s due to incompatible API version (uses %d, but current is %s)"
                                  % (p.name(), p.apiVersion(), _CurrentAPIVersion))
                    continue

                if not p.prefix():
                    cmdout.warn("failed to load plugin %s because prefix is empty" % p.name())

                if "." in p.prefix() or " " in p.prefix():
                    cmdout.warn("failed to load plugin %s because prefix contains dots or spaces" % p.name())

                # Need to convert prefix to lowercase here, because a plugin
                # can override the prefix() method and might not return a
                # lowercase string.  Also, we don't allow two plugins to have
                # prefixes that differ only by case (due to the fact that
                # plugin option names include the prefix and are converted
                # to lowercase).
                pluginprefix = p.prefix().lower()

                sameprefix = False
                for i in self._plugins:
                    if pluginprefix == i.prefix().lower():
                        sameprefix = True
                        cmdout.warn("failed to load plugin %s (prefix %s) due to plugin %s (prefix %s) having the same prefix" % (p.name(), p.prefix(), i.name(), i.prefix()))
                        break

                if not sameprefix:
                    self._plugins += [p]

        if not found:
            cmdout.warn("no plugin found in %s" % module.__file__)

