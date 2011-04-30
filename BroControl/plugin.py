#
# BroControl Plugin API.
#

import pluginreg
import config
import util

Registry = pluginreg.PluginRegistry()

class Plugin:
    """Base class for all BroControl plugins.

    The class has a number of methods for plugins to override, and every
    plugin must at least override ``name()`` and ``version()``.

    For each BroControl command ``foo``, there's are two methods,
    ``cmd_foo_pre`` and ``cmd_foo_post``, that are called just before the
    command is executed and just after it has finished, respectivey. The
    arguments these methods receive correspond to their command-line
    parameters, and are further documented belows.

    The ``cmd_<XXX>_pre`` methods have the ability to prevent the command's
    execution, either completely or partially for those commands that take
    nodes as parameters. In the latter case, the method receives a list of
    nodes that the command is to be run on, and it can filter that list and
    returns modified version of nodes actually to use. The standard case would
    be returning simply the unmodified ``nodes`` parameter. To completely
    block the command's execution, return an empty list. To just not execute
    the command for a subset, remove them affected ones.  For commands that do
    not receive nodes as arguments, the return value is interpreted as boolean
    indicated whether command execution should proceed (True) or not (False).

    The ``cmd_<XXX>_post`` methods likewise receive the commands arguments as
    their parameter, as documented below. For commands taking nodes, the list
    corresponds to those nodes for which the command was actually executed
    (i.e., after any ``cmd_<XXX>_pre`` filtering). Each node is given as a
    tuple ``(node, bool)`` with *node* being the actual node, and the boolean
    indicating whether the command was succesful for it.

    Note that if plugin prevent a command from execution either completely or
    partially, it should report its reason via the ``message*(`` or
    ``error()`` methods.

    If multiple plugins hook into the same command, all their
    ``cmd_<XXX>_{pre,post}`` are executed in undefined order. The command is
    executed on the intersection of all ``cmd_<XXX>_pre`` results.
    """

    def getGlobalOption(self, name):
        """Returns the value of the global BroControl option *name*. If the
        user has not set the options, its default value is returned."""
        if config.Config.hasAttr(name):
            raise KeyError

        return config.Config.__getattr(name)

    def getOption(self, name):
        """Returns the value of one of the plugin's options, *name*. The
        returned value will always be a string.

        An option has a default value (see *options()*), which can be
        overridden by a user in ``broctl.cfg``. An option's value cannot be
        changed by the plugin.
        """
        name = "%s.%s" % (self.prefix().lower(), name.lower())

        if not config.Config.hasAttr(name):
            raise KeyError

        return config.Config.__getattr__(name)

    def getState(self, name):
        """Returns the current value of one of the plugin's state variables,
        *name*. The returned value will always be a string. If it has not yet
        been set, an empty string will be returned.

        Different from options, state variables can be set by the plugin and
        are persistent across restarts. They are not visible to the user.

        Note that a plugin cannot query any global BroControl state variables.
        """
        name = "%s.state.%s" % (self.prefix().lower(), name.lower())

        if not config.Config.hasAttr(name):
            return ""

        return config.Config.__getattr__(name)

    def setState(self, name, value):
        """Sets the one of the plugin's state variables, *name*, to *value*.
        *value* must be a string. The change is permanent and will be recorded
        to disk.

        Note that a plugin cannot change any global BroControl state
        variables.
        """
        if not isinstance(value, str):
            self.error("values for a plugin state variable must be strings")

        if "." in name or " " in name:
            self.error("plugin state variable names must not contain dots or spaces")

        name = "%s.state.%s" % (self.prefix().lower(), name.lower())
        config.Config._setState(name, value)

    def getNodes(self, names):
        """Returns *Node* objects for a string of space-separated node names.
        If a name does not correspond to know node, an error message is
        printed and the node is skipped from the returned list. If not names
        are known, an empty list is returned."""
        nodes = []

        for arg in names.split():
            h = config.Config.nodes(arg, True)
            if not h:
                util.output("unknown node '%s'" % arg)
            else:
                nodes += [h]

        return nodes

    def message(self, msg):
        """Reports a message to the user."""
        util.output(msg, prefix=self.name()[1])

    def debug(self, msg):
        """Logs a debug message in BroControl' debug log if enabled."""
        util.debug(msg, prefix=self.name()[1])

    def error(self, msg):
        """Reports an error to the user."""
        output("error: %s" % msg, prefix=self.name()[1])

    def execute(self, node, cmd):
        """Executes a command on the given *node* of type *Node*. Returns a
        tuple ``(rc, output)`` in which ``rc`` is the command's exit code and
        ``output`` the combined stdout/stderr output."""
        control.executeCmdsParallel([node, cmd])

    def executeParallel(self, cmds):
        """Executes a set of commands in parallel on multiple nodes. ``cmds``
        is a list of tuples ``(node, cmd)``, in which the *node* is *Node*
        instance and *cmd* a string with the command to execute for it. The
        method returns a list of tuples ``(node, rc, output)``, in which
        ``rc`` is the exit code and ``output`` the combined stdout/stderr
        output for the corresponding ``node``."""
        control.executeCmdsParallel(cmds)

    ### Methods that must be overridden by plugins.

    def name(self):
        """Returns a a strings with a descriptive *name* for the plugin (e.g.,
        ``"TestPlugin"``). The name must not contain any white-space.

        This method must be overridden by derived classes. The implementation
        must not call the parent class' implementation.
        """
        raise NotImplementedError

    def version(self):
        """
        Returns an integer with a version number for the plugin.

        This method must be overridden by derived classes. The implementation
        must not call the parent class' implementation.
        """
        raise NotImplementedError

    def prefix(self):
        """Returns a string with a prefix for the plugin's options and
        commands names (e.g., "myplugin")``).

        This method can be overridden by derived classes. The implementation
        must not call the parent class' implementation. The default
        implementation returns a lower-cased version of *name()*.
        """
        return self.name().lower()

    def options(self):
        """Returns a set of local configuration options provided by the
        plugin.

        The return value is a list of 4-tuples each having the following
        elements:

            ``name``
                A string with name of the option (e.g., ``Path``). Option
                names are case-insensitive. Note that the option name exposed
                to the user will be prefixed with your plugin's prefix as
                returned by *name()* (e.g., ``myplugin.Path``).

            ``type``
                A string with type of the option, which must be one of
                ``"bool"``, ``"string"``, or ``"int"``.

            ``default``
                A string with the option's default value. Note that this must
                always be a string, even for non-string types. For booleans,
                use ``"0"`` for False and ``"1"`` for True. For integers, give
                the value as a string ``"42"``.

            ``description``
                A string with a description of the option semantics.

        This method can be overridden by derived classes. The implementation
        must not call the parent class' implementation. The default
        implementation returns an empty list.
        """
        return []

    def commands(self):
        """Returns a set of custom commands provided by the
        plugin.

        The return value is a list of 2-tuples each having the following
        elements:

            ``command``
                A string with the command's name. Note that command name
                exposed to the user will be prefixed with the plugin's prefix
                as returned by *name()* (e.g., ``myplugin.mycommand``).

            ``description``
                A string with a description of the command's semantics.


        This method can be overridden by derived classes. The implementation
        must not call the parent class' implementation. The default
        implementation returns an empty list.
        """
        return []

    def init(self):
        """Called once just before BroControl starts executing any commands.
        This method can do any initialization that the plugin may require.

        Note that at when this method executes, BroControl guarantees that all
        internals are fully set up (e.g., user-defined options are available).
        This may not be the case when the class ``__init__`` method runs.

        Returns a boolean, indicating whether the plugin should be used. If it
        returns ``False``, the plugin will be removed and no other methods
        called.

        This method can be overridden by derived classes. The default
        implementation always returns True.
        """
        return True

    def done(self):
        """Called once just before BroControl terminates. This method can do
        any cleanup the plugin may require.
        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return

    def cmd_check_pre(self, nodes):
        """Called just before the ``check`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    def cmd_check_post(self, nodes):
        """Called just after the ``check`` command has finished. It receives
        the list of 2-tuples ``(node, bool)`` indicating the nodes the command
        was executed for, along with their success status.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    def cmd_custom(self, cmd, args):
        """Called when command defined by the ``commands`` method is executed.
        ``cmd`` is the command (with the plugin's prefix), and ``args`` is a
        single *string* with all arguments.

        If the arguments are actually node names, ``getNodes`` can
        be used to get the Node objects.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    # Internal methods.

    def _registerOptions(self):
        if ( not self.prefix() ):
            self.error("plugin prefix must not be empty")

        if "." in self.prefix() or " " in self.prefix():
            self.error("plugin prefix must not contain dots or spaces")

        for (name, ty, default, descr) in self.options():
            if ( not name ):
                self.error("plugin option names must not be empty")

            if "." in name or " " in name:
                self.error("plugin option names must not contain dots or spaces")

            if not isinstance(default, str):
                self.error("plugin option default must be a string")

            config.Config._setOption("%s.%s" % (self.prefix().lower(), name), default)
