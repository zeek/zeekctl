#
# ZeekControl Plugin API.
#

from __future__ import print_function
import logging

from ZeekControl import config
from ZeekControl import doc

class Plugin(object):
    """The class ``Plugin`` is the base class for all ZeekControl plugins.

    The class has a number of methods for plugins to override, and every
    plugin must at least override ``name()`` and ``pluginVersion()``.

    For each ZeekControl command ``foo``, there are two methods,
    ``cmd_foo_pre`` and ``cmd_foo_post``, that are called just before the
    command is executed and just after it has finished, respectively. The
    arguments these methods receive correspond to their command-line
    parameters, and are further documented below.

    The ``cmd_<XXX>_pre`` methods have the ability to prevent the command's
    execution, either completely or partially for those commands that take
    nodes as parameters. In the latter case, the method receives a list of
    nodes that the command is to be run on, and it can filter that list and
    returns modified version of nodes to actually use. The standard case would
    be returning simply the unmodified ``nodes`` parameter. To completely
    block the command's execution, return an empty list. To just not execute
    the command for a subset, remove the affected ones.  For commands that do
    not receive nodes as arguments, the return value is interpreted as boolean
    indicating whether command execution should proceed (True) or not (False).

    The ``cmd_<XXX>_post`` methods likewise receive the commands arguments as
    their parameter, as documented below. For commands taking nodes, the list
    corresponds to those nodes for which the command was actually executed
    (i.e., after any ``cmd_<XXX>_pre`` filtering).

    Note that if a plugin prevents a command from executing either completely or
    partially, it should report its reason via the ``message()`` or
    ``error()`` methods.

    If multiple plugins hook into the same command, all their
    ``cmd_<XXX>_{pre,post}`` are executed in undefined order. The command is
    executed on the intersection of all ``cmd_<XXX>_pre`` results.

    Finally, note that the ``restart`` command is just a combination of other
    commands and thus their callbacks are run in addition to the callbacks
    for ``restart``.
    """

    def __init__(self, apiversion):
        """Must be called by the plugin with the plugin API version it
        expects to use. The version currently documented here is 1."""
        self._apiversion = apiversion
        self.activated = False

    def apiVersion(self):
        """Returns the plugin API that the plugin expects to use."""
        return self._apiversion

    @doc.api
    def getGlobalOption(self, name):
        """Returns the value of the global ZeekControl option *name*.

        See the output of ``zeekctl config`` for a complete list."""
        val = config.Config.get_option(name)
        if val is None:
            raise KeyError("plugin %s lookup of unknown config option %s" % (self.name(), name))

        return val

    @doc.api
    def getOption(self, name):
        """Returns the value of one of the plugin's options, *name*.

        An option has a default value (see *options()*), which can be
        overridden by a user in ``zeekctl.cfg``. An option's value cannot be
        changed by the plugin.
        """
        name = "%s.%s" % (self.prefix(), name)

        val = config.Config.get_option(name)
        if val is None:
            raise KeyError("plugin %s lookup of unknown plugin option %s" % (self.name(), name))

        return val

    @doc.api
    def getState(self, name):
        """Returns the current value of one of the plugin's state variables,
        *name*. If it has not yet been set, an empty string will be returned.

        Different from options, state variables can be set by the plugin.
        They are persistent across restarts.

        Note that a plugin cannot query any global ZeekControl state variables.
        """
        name = "%s.state.%s" % (self.prefix(), name)

        return config.Config.get_state(name, "")

    @doc.api
    def setState(self, name, value):
        """Sets one of the plugin's state variables, *name*, to *value*.
        The change is permanent and will be recorded to disk.

        Note that a plugin cannot change any global ZeekControl state
        variables.
        """
        if "." in name or " " in name:
            self.error('plugin %s state variable name "%s" must not contain dots or spaces' % (self.name(), name))
            return

        name = "%s.state.%s" % (self.prefix(), name)
        config.Config.set_state(name, value)

    @doc.api
    def parseNodes(self, names):
        """Returns a tuple which contains two lists. The first list is a list
        of `Node`_ objects for a string of space-separated node names. If a
        name does not correspond to a known node, then the name is added
        to the second list in the returned tuple.
        """
        nodes = []
        notnodes = []

        for arg in names.split():
            nodelist = config.Config.nodes(arg)
            if nodelist:
                nodes += nodelist
            else:
                notnodes.append(arg)

        # Sort the list so that it doesn't depend on initial order of arguments
        nodes.sort(key=lambda n: (n.type, n.name))

        return (nodes, notnodes)

    @doc.api
    def message(self, msg):
        """Reports a message to the user."""
        print("%s" % msg)

    @doc.api
    def debug(self, msg):
        """Logs a debug message in ZeekControl's debug log if enabled."""
        logging.debug("%s: %s", self.prefix(), msg)

    @doc.api
    def error(self, msg):
        """Reports an error to the user."""
        print("error: %s" % msg)

    @doc.api
    def execute(self, node, cmd):
        """Executes a command on the host for the given *node* of type
        `Node`_. Returns a tuple ``(success, output)`` in which ``success`` is
        True if the command ran successfully, and ``output`` is a string
        which contains the combined stdout/stderr output."""

        resultlist = self.executor.run_shell_cmds([(node, cmd)])
        if resultlist:
            _, success, output = resultlist[0]
        else:
            success = False
            output = ""

        return (success, output)

    @doc.api
    def nodes(self):
        """Returns a list of all configured `Node`_ objects."""
        return config.Config.nodes()

    @doc.api
    def hosts(self, nodes=[]):
        """Returns a list of Node_ objects which is a subset of the list in
        *nodes*, such that only one node per host will be chosen.  If *nodes*
        is empty, then the returned list will be a subset of the entire list
        of configured nodes."""

        if not nodes:
            return [n for n in config.Config.hosts()]

        result = []
        h = {}

        for n in nodes:
            if n.host not in h:
                h[n.host] = 1
                result.append(n)

        return result

    @doc.api
    def executeParallel(self, cmds):
        """Executes a set of commands in parallel on multiple hosts. ``cmds``
        is a list of tuples ``(node, cmd)``, in which the *node* is a `Node`_
        instance and *cmd* is a string with the command to execute for it. The
        method returns a list of tuples ``(node, success, output)``, in which
        ``success`` is True if the command ran successfully, and ``output`` is
        a string containing the combined stdout/stderr output for the
        corresponding ``node``."""

        return self.executor.run_shell_cmds(cmds)

    ### Methods that must be overridden by plugins.

    @doc.api("override")
    def name(self):
        """Returns a string with a descriptive name for the plugin (e.g.,
        ``"TestPlugin"``). The name must not contain any whitespace.

        This method must be overridden by derived classes. The implementation
        must not call the parent class' implementation.
        """
        raise NotImplementedError

    @doc.api("override")
    def pluginVersion(self):
        """
        Returns an integer with a version number for the plugin. Plugins
        should increase their version number with any significant change.

        This method must be overridden by derived classes. The implementation
        must not call the parent class' implementation.
        """
        raise NotImplementedError

    ### Methods that can be overridden by plugins.

    @doc.api("override")
    def prefix(self):
        """Returns a string with a prefix for the plugin's options and
        commands names (e.g., "myplugin").  The prefix cannot contain
        any whitespace or dots (because dots are used as separators when
        forming the plugin's option names, state variable names, and
        command names).

        Note that ZeekControl will refuse to load a plugin if its prefix
        matches the prefix of another loaded plugin (this comparison is not
        case-sensitive).

        This method can be overridden by derived classes. The implementation
        must not call the parent class' implementation. The default
        implementation returns a lower-cased version of *name()*.
        """
        return self.name().lower()

    @doc.api("override")
    def options(self):
        """Returns a set of local configuration options provided by the
        plugin.

        The return value is a list of 4-tuples each having the following
        elements:

            ``name``
                A string with name of the option (e.g., ``Path``). Option
                names are not case-sensitive. Note that the option name exposed
                to the user will be prefixed with your plugin's prefix as
                returned by *prefix()* (e.g., ``myplugin.Path``).

            ``type``
                A string with type of the option, which must be one of
                ``"bool"``, ``"string"``, or ``"int"``.

            ``default``
                The option's default value.  Note that this value must be
                enclosed in quotes if the type is "string", and must not be
                enclosed in quotes if the type is not "string".

            ``description``
                A string with a description of the option semantics.

        This method can be overridden by derived classes. The implementation
        must not call the parent class' implementation. The default
        implementation returns an empty list.
        """
        return []

    @doc.api("override")
    def commands(self):
        """Returns a set of custom commands provided by the
        plugin.

        The return value is a list of 3-tuples each having the following
        elements:

            ``command``
                A string with the command's name. Note that the command name
                exposed to the user will be prefixed with the plugin's prefix
                as returned by *prefix()* (e.g., ``myplugin.mycommand``, or
                just ``myplugin`` if the command name is an empty string).

            ``arguments``
                A string describing the command's arguments in a textual form
                suitable for use in the ``help`` command summary (e.g.,
                ``[<nodes>]`` for a command taking an optional list of nodes).
                Empty if no arguments are expected.

            ``description``
                A string with a description of the command's semantics suitable
                for use in the ``help`` command summary.


        This method can be overridden by derived classes. The implementation
        must not call the parent class' implementation. The default
        implementation returns an empty list.
        """
        return []

    @doc.api("override")
    def nodeKeys(self):
        """Returns a list of names of custom keys for nodes (the value of a
        key can be specified in ``node.cfg`` for any node defined there).
        Node key names are not case-sensitive.

        The value for a key will be available from the `Node`_ object as
        attribute ``<prefix>_<key>`` (e.g., ``node.myplugin_mykey``). If not
        set, the attribute will be set to an empty string.

        This method can be overridden by derived classes. The implementation
        must not call the parent class' implementation. The default
        implementation returns an empty list.
        """
        return []

    @doc.api("override")
    def zeekctl_config(self):
        """Returns a string containing Zeek script code that should be written
        to the dynamically generated Zeek script named "zeekctl-config.zeek".
        This provides a way for plugins to easily add Zeek script code that
        depends on zeekctl settings.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return

    def broctl_config(self):
        """Deprecated legacy name for `zeekctl_config`."""
        return

    @doc.api("override")
    def init(self):
        """Called once just before ZeekControl starts executing any commands.
        This method can do any initialization that the plugin may require.

        Note that when this method executes, ZeekControl guarantees that all
        internals are fully set up (e.g., user-defined options are available).
        This may not be the case when the class ``__init__`` method runs.

        Returns a boolean, indicating whether the plugin should be used. If it
        returns ``False``, the plugin will be removed and no other methods
        called.

        This method can be overridden by derived classes. The default
        implementation always returns True.
        """
        return True

    @doc.api("override")
    def done(self):
        """Called once just before ZeekControl terminates. This method can do
        any cleanup the plugin may require.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return

    @doc.api("override")
    def hostStatusChanged(self, host, status):
        """Called when ZeekControl's ``cron`` command finds the availability of
        a cluster system to have changed. Initially, all systems are assumed
        to be up and running. Once ZeekControl notices that a system isn't
        responding (defined as not accepting SSH sessions), it calls
        this method, passing in a string with
        the name of the *host* and a boolean *status* set to False. Once the
        host becomes available again, the method will be called again for the
        same host with *status* now set to True.

        Note that ZeekControl's ``cron`` tracks a host's availability across
        execution, so if the next time it's run the host is still down, this
        method will not be called again.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return

    @doc.api("override")
    def zeekProcessDied(self, node):
        """Called when ZeekControl finds the Zeek process for Node_ *node*
        to have terminated unexpectedly. This method will be called just
        before ZeekControl prepares the node's "crash report" and before it
        cleans up the node's spool directory.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return

    def broProcessDied(self, node):
        """Deprecated legacy name for `zeekProcessDied`."""
        # We keep this around as it's difficult to warn about its usage.
        return

    # Per-command help currently not supported by zeekctl. May add this later.
    #
    #@doc.api(override):
    #def help_custom(self, cmd):
    #    """Called for getting the ``help`` text for a custom command defined
    #    by Plugin.commands_. Returns a string with the text, or an empty
    #    string if no help is available.
    #
    #    This method can be overridden by derived classes. The default
    #    implementation always returns an empty string.
    #    """
    #    return ""

    @doc.api("override")
    def cmd_nodes_pre(self):
        """Called just before the ``nodes`` command is run. Returns a
        boolean indicating whether or not the command should run.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return True

    @doc.api("override")
    def cmd_nodes_post(self):
        """Called just after the ``nodes`` command has finished.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_config_pre(self):
        """Called just before the ``config`` command is run. Returns a boolean
        indicating whether or not the command should run.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return True

    @doc.api("override")
    def cmd_config_post(self):
        """Called just after the ``config`` command has finished.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_exec_pre(self, cmdline):
        """Called just before the ``exec`` command is run. *cmdline* is a
        string with the command line to execute.

        Returns a boolean indicating whether or not the ``exec`` command
        should run.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return True

    @doc.api("override")
    def cmd_exec_post(self, cmdline):
        """Called just after the ``exec`` command has finished. Arguments are
        as with the ``pre`` method.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_install_pre(self):
        """Called just before the ``install`` command is run. Returns a
        boolean indicating whether or not the command should run.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return True

    @doc.api("override")
    def cmd_install_post(self):
        """Called just after the ``install`` command has finished.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_cron_pre(self, arg, watch):
        """Called just before the ``cron`` command is run. *arg* is an empty
        string if the command is executed without arguments. Otherwise, it is
        one of the strings: ``enable``, ``disable``, ``?``. *watch* is a
        boolean indicating whether the ``cron`` command should restart
        abnormally terminated Zeek processes; it's only valid if *arg* is empty.

        Returns a boolean indicating whether or not the ``cron`` command should
        run.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return True

    @doc.api("override")
    def cmd_cron_post(self, arg, watch):
        """Called just after the ``cron`` command has finished. Arguments are
        as with the ``pre`` method.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_check_pre(self, nodes):
        """Called just before the ``check`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_check_post(self, results):
        """Called just after the ``check`` command has finished. It receives
        the list of 2-tuples ``(node, bool)`` indicating the nodes the command
        was executed for, along with their success status.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_start_pre(self, nodes):
        """Called just before the ``start`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_start_post(self, results):
        """Called just after the ``start`` command has finished. It receives
        the list of 2-tuples ``(node, bool)`` indicating the nodes the command
        was executed for, along with their success status.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_stop_pre(self, nodes):
        """Called just before the ``stop`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_stop_post(self, results):
        """Called just after the ``stop`` command has finished. It receives
        the list of 2-tuples ``(node, bool)`` indicating the nodes the command
        was executed for, along with their success status.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_deploy_pre(self):
        """Called just before the ``deploy`` command is run. Returns a
        boolean indicating whether or not the command should run.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return True

    @doc.api("override")
    def cmd_deploy_post(self):
        """Called just after the ``deploy`` command has finished.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_status_pre(self, nodes):
        """Called just before the ``status`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_status_post(self, nodes):
        """Called just after the ``status`` command has finished.  Arguments
        are as with the ``pre`` method.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_update_pre(self, nodes):
        """Called just before the ``update`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_update_post(self, results):
        """Called just after the ``update`` command has finished. It receives
        the list of 2-tuples ``(node, bool)`` indicating the nodes the command
        was executed for, along with their success status.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_custom(self, cmd, args, cmdout):
        """Called when a command defined by the ``commands`` method is executed.
        *cmd* is the command (without the plugin's prefix), and *args* is a
        single string with all arguments.  It returns a CmdResult object
        containing the command results.

        If the arguments are actually node names, ``parseNodes`` can
        be used to get the `Node`_ objects.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_df_pre(self, nodes):
        """Called just before the ``df`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_df_post(self, nodes):
        """Called just after the ``df`` command has finished. Arguments are as
        with the ``pre`` method.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_diag_pre(self, nodes):
        """Called just before the ``diag`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_diag_post(self, nodes):
        """Called just after the ``diag`` command has finished. Arguments are
        as with the ``pre`` method.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_peerstatus_pre(self, nodes):
        """Called just before the ``peerstatus`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_peerstatus_post(self, nodes):
        """Called just after the ``peerstatus`` command has finished.
        Arguments are as with the ``pre`` method.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_netstats_pre(self, nodes):
        """Called just before the ``netstats`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_netstats_post(self, nodes):
        """Called just after the ``netstats`` command has finished. Arguments
        are as with the ``pre`` method.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_top_pre(self, nodes):
        """Called just before the ``top`` command is run. It receives the list
        of nodes, and returns the list of nodes that should proceed with the
        command. Note that when ``top`` is run interactively to auto-refresh
        continuously, this method will be called once before each update.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_top_post(self, nodes):
        """Called just after the ``top`` command has finished. Arguments are
        as with the ``pre`` method. Note that when ``top`` is run
        interactively to auto-refresh continuously, this method will be called
        once after each update.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_restart_pre(self, nodes, clean):
        """Called just before the ``restart`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command. *clean* is boolean indicating whether the ``--clean``
        argument has been given.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_restart_post(self, nodes):
        """Called just after the ``restart`` command has finished. It receives
        a list of *nodes* indicating the nodes on which the command was
        executed.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_cleanup_pre(self, nodes, all):
        """Called just before the ``cleanup`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command. *all* is boolean indicating whether the ``--all``
        argument has been given.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_cleanup_post(self, nodes, all):
        """Called just after the ``cleanup`` command has finished. Arguments
        are as with the ``pre`` method.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_capstats_pre(self, nodes, interval):
        """Called just before the ``capstats`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command. *interval* is an integer with the measurement interval in
        seconds.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_capstats_post(self, nodes, interval):
        """Called just after the ``capstats`` command has finished. Arguments
        are as with the ``pre`` method.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_scripts_pre(self, nodes, check):
        """Called just before the ``scripts`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command. *check* is boolean indicating whether the ``-c``
        option was given.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_scripts_post(self, nodes, check):
        """Called just after the ``scripts`` command has finished. Arguments
        are as with the ``pre`` method.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_print_pre(self, nodes, id):
        """Called just before the ``print`` command is run. It receives the
        list of nodes, and returns the list of nodes that should proceed with
        the command. *id* is a string with the name of the ID to be printed.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_print_post(self, nodes, id):
        """Called just after the ``print`` command has finished. Arguments are
        as with the ``pre`` method.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    @doc.api("override")
    def cmd_process_pre(self, trace, options, scripts):
        """Called just before the ``process`` command is run. It receives the
        *trace* to read from as a string, a list of additional Zeek *options*,
        and a list of additional Zeek *scripts*.

        Returns a boolean indicating whether or not the ``process`` command
        should run.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        return True

    @doc.api("override")
    def cmd_process_post(self, trace, options, scripts, success):
        """Called just after the ``process`` command has finished. Arguments
        are as with the ``pre`` method, plus an additional boolean *success*
        indicating whether Zeek terminated normally.

        This method can be overridden by derived classes. The default
        implementation does nothing.
        """
        pass

    # Internal methods.

    def _to_bool(self, val):
        if val.lower() in ("1", "true"):
            return True
        if val.lower() in ("0", "false"):
            return False
        raise ValueError("invalid boolean: '%s'" % val)


    def _registerOptions(self):
        type_converters = {"bool": self._to_bool, "int": int, "string": str}
        pytype = {"bool": bool, "int": int, "string": str}

        for (name, ty, default, descr) in self.options():
            if not name:
                self.error("plugin %s option name must not be empty" % self.name())
                continue

            if "." in name or " " in name:
                self.error('plugin %s option name "%s" must not contain dots or spaces' % (self.name(), name))
                continue

            optname = "%s.%s" % (self.prefix(), name)

            if ty not in pytype:
                self.error('plugin option %s has invalid type "%s"' % (optname, ty))
                continue

            if not isinstance(default, pytype[ty]):
                self.error("plugin option %s default value must be type %s" % (optname, ty))
                continue

            val = config.Config.get_option(optname)
            if val is not None:
                # Convert option values to correct data type for options
                # specified in zeekctl.cfg
                try:
                    newval = type_converters[ty](val)
                except ValueError:
                    self.error('zeekctl option "%s" has invalid value "%s" for type %s' % (optname, val, ty))
                    continue

                config.Config.set_option(optname, newval)
            else:
                # Set default value for options not specified in zeekctl.cfg
                config.Config.init_option(optname, default)
