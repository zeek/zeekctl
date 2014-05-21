#! /usr/bin/env python
#
# The BroControl interactive shell.

import os
import sys
import cmd
import time
import platform
import atexit

from BroControl import util
from BroControl import config
from BroControl import execute
from BroControl import install
from BroControl import control
from BroControl import cron
from BroControl import plugin
from BroControl.config import Config

class InvalidNode(Exception):
    pass

class TermUI:
    def __init__(self):
        pass

    def output(self, txt):
        print txt
    info = output
    debug = output

    def error(self, txt):
        print >>sys.stderr, txt
    warn = error

def expose(func):
    func.api_exposed = True
    return func

def lock_required(func):
    func.lock_required = True
    return func

class BroCtl(object):
    def __init__(self, basedir="/bro", ui=TermUI(), state=None):
        self.ui = ui
        self.BroBase = basedir


        self._locked = False
        self._failed = False

        self.config = config.Configuration(self.BroBase, self.ui, state)
        self.setup()
        self.controller = control.Controller(self.config, self.ui)

    def setup(self):

        for dir in self.config.sitepluginpath.split(":") + [self.config.plugindir]:
            if dir:
                plugin.Registry.addDir(dir)

        plugin.Registry.loadPlugins(self.ui)
        self.config.initPostPlugins(self.ui)
        plugin.Registry.initPlugins()
        util.enableSignals()
        os.chdir(self.config.brobase)

        self.plugins = plugin.Registry

    # Turns nodes arguments into a list of node names.
    def nodeArgs(self, args=None):
        if not args:
            args = "all"

        nodes = []

        for arg in args.split():
            h = self.config.nodes(arg)
            if not h and arg != "all":
                raise InvalidNode("unknown node '%s'" % arg)

            nodes += h

        return nodes

    # Turns node name arguments into a list of nodes.  The result is a subset of
    # a similar call to nodeArgs() but here only one node is chosen for each host.
    def nodeHostArgs(self, args=None):
        if not args:
            args = "all"

        hosts = {}
        nodes = []

        for arg in args.split():
            h = self.config.hosts(arg)
            if not h and arg != "all":
                raise InvalidNode("unknown node '%s'" % arg)

            for node in h:
                if node.host not in hosts:
                    hosts[node.host] = 1
                    nodes.append(node)

        return nodes

    def output(self, text):
        self.ui.info(text)

    def error(self, text):
        self.ui.error(text)

    def syntax(self, args):
        self.errror("Syntax error: %s" % args)

    def lock(self):
        lockstatus = util.lock(self.ui)
        if not lockstatus:
            sys.exit(1)

        self._locked = True
        statestatus = self.config.readState(self.ui)
        if not statestatus:
            sys.exit(1)
        self.config.config["sigint"] = "0"

    def precmd(self, line):
        util.debug(1, line, prefix="command")
        self._locked = False
        self._failed = False
        return line

    def checkForFailure(self, results):
        if control.nodeFailed(results):
            self._failed = True
            self.exit_code = 1
            return False
        return True

    def failed(self):
        return self._failed

    def postcmd(self, stop, line):
        self.config.writeState(self.ui)
        if self._locked:
            util.unlock(self.ui)
            self._locked = False

        execute.clearDeadHostConnections()
        util.debug(1, "done", prefix="command")
        return stop

    @expose
    def nodes(self):
        """Prints a list of all configured nodes."""
        nodes = []
        if self.plugins.cmdPre("nodes"):
            nodes = self.config.nodes()
        self.plugins.cmdPost("nodes")
        return nodes

    @expose
    def get_config(self):
        """Prints all configuration options with their current values."""

        config = {}
        if self.plugins.cmdPre("config"):
            config = self.config.options()

        self.plugins.cmdPost("config")
        return config

    @expose
    @lock_required
    def install(self, local=False):
        """- [--local]

        Reinstalls on all nodes (unless the ``--local`` option is given, in
        which case nothing will be propagated to other nodes), including all
        configuration files and local policy scripts.  Usually all nodes
        should be reinstalled at the same time, as any inconsistencies between
        them will lead to strange effects.  This command must be
        executed after *all* changes to any part of the broctl configuration
        (and after upgrading to a new version of Bro or BroControl),
        otherwise the modifications will not take effect.  Before executing
        ``install``, it is recommended to verify the configuration
        with check_."""

        if self.plugins.cmdPre("install"):
            cmdSuccess = install.install(local, self.ui)

        self.plugins.cmdPost("install")
        return cmdSuccess

    @expose
    @lock_required
    def start(self, node_list=None):
        """- [<nodes>]

        Starts the given nodes, or all nodes if none are specified. Nodes
        already running are left untouched.
        """

        nodes = self.nodeArgs(node_list)

        nodes = self.plugins.cmdPreWithNodes("start", nodes)
        results = self.controller.start(nodes)
        status = self.checkForFailure(results)
        self.plugins.cmdPostWithResults("start", results)
        return status

    @expose
    @lock_required
    def stop(self, node_list=None):
        """- [<nodes>]

        Stops the given nodes, or all nodes if none are specified. Nodes not
        running are left untouched.
        """

        nodes = self.nodeArgs(node_list)

        nodes = self.plugins.cmdPreWithNodes("stop", nodes)
        results = self.controller.stop(nodes)
        status = self.checkForFailure(results)
        self.plugins.cmdPostWithResults("stop", results)
        return status

    @expose
    @lock_required
    def restart(self, node_list=None, clean=False):
        """- [--clean] [<nodes>]

        Restarts the given nodes, or all nodes if none are specified. The
        effect is the same as first executing stop_ followed
        by a start_, giving the same nodes in both cases.
        This command is most useful to activate any changes made to Bro policy
        scripts (after running install_ first). Note that a
        subset of policy changes can also be installed on the fly via
        update_, without requiring a restart.

        If ``--clean`` is given, the installation is reset into a clean state
        before restarting. More precisely, a ``restart --clean`` turns into
        the command sequence stop_, cleanup_, check_, install_, and
        start_.
        """

        nodes = self.nodeArgs(node_list)

        nodes = self.plugins.cmdPreWithNodes("restart", nodes, clean)
        args = " ".join([ str(n) for n in nodes ])

        self.output("stopping ...")
        success = self.stop(node_list)
        self.postcmd(False, node_list) # Need to call manually.

        if not success:
            return False

        if clean:
            self.output("cleaning up ...")
            success = self.cleanup(node_list)
            self.postcmd(False, node_list)

            if not success:
                return False

            self.output("checking configurations...")
            success = self.check(node_list)
            self.postcmd(False, node_list)

            if not success:
                return False

            util.output("installing ...")
            success = self.install()
            self.postcmd(False, node_list)

            if not success:
                return False

        self.output("starting ...")
        success = self.start(node_list)
        self.postcmd(False, node_list)

        self.plugins.cmdPostWithNodes("restart", nodes)
        return success

    @expose
    @lock_required
    def status(self, node_list=None):
        """- [<nodes>]

        Prints the current status of the given nodes."""

        nodes = self.nodeArgs(node_list)

        nodes = self.plugins.cmdPreWithNodes("status", nodes)
        node_infos = self.controller.status(nodes)
        self.plugins.cmdPostWithNodes("status", nodes)
        return node_infos

    def _do_top_once(self, args):
        cmdout = cmdoutput.CommandOutput()
        lockstatus = util.lock(cmdout)
        if lockstatus:
            # Read state again (may have changed by cron in the meantime).
            if not Config.readState(cmdout):
                cmdout.printResults()
                sys.exit(1)

            nodes = self.nodeArgs(args)

            nodes = self.plugins.cmdPreWithNodes("top", nodes)
            cmdSuccess, cmdOutput = control.top(nodes)
            cmdout.append(cmdOutput)
            self.plugins.cmdPostWithNodes("top", nodes)

            util.unlock(cmdout)

        cmdout.printResults()
        return cmdSuccess

    def do_top(self, args):
        """- [<nodes>]

        For each of the nodes, prints the status of the two Bro
        processes (parent process and child process) in a *top*-like
        format, including CPU usage and memory consumption. If
        executed interactively, the display is updated frequently
        until key ``q`` is pressed. If invoked non-interactively, the
        status is printed only once."""

        self.lock()

        if not Interactive:
            self._do_top_once(args)
            return

        cmdout = cmdoutput.CommandOutput()
        util.unlock(cmdout)
        cmdout.printResults()

        util.enterCurses()
        util.clearScreen()

        count = 0

        while config.Config.sigint != "1" and util.getCh() != "q":
            if count % 10 == 0:
                util.bufferOutput()
                self._do_top_once(args)
                lines = util.getBufferedOutput()
                util.clearScreen()
                util.printLines(lines)
            time.sleep(.1)
            count += 1

        util.leaveCurses()

        lockstatus = util.lock(cmdout)
        cmdout.printResults()

        if not lockstatus:
            sys.exit(1)

        return False

    def do_diag(self, args):
        """- [<nodes>]

        If a node has terminated unexpectedly, this command prints a (somewhat
        cryptic) summary of its final state including excerpts of any
        stdout/stderr output, resource usage, and also a stack backtrace if a
        core dump is found. The same information is sent out via mail when a
        node is found to have crashed (the "crash report"). While the
        information is mainly intended for debugging, it can also help to find
        misconfigurations (which are usually, but not always, caught by the
        check_ command)."""

        self.lock()
        nodes = self.nodeArgs(args)

        nodes = self.plugins.cmdPreWithNodes("diag", nodes)

        success = True

        for h in nodes:
            cmdSuccess, cmdOutput = control.crashDiag(h)
            success = success and cmdSuccess
            cmdOutput.printResults()

        self.plugins.cmdPostWithNodes("diag", nodes)

        return success

    def do_attachgdb(self, args):
        """- [<nodes>]

        Primarily for debugging, the command attaches a *gdb* to the main Bro
        process on the given nodes. """

        self.lock()
        nodes = self.nodeArgs(args)
        nodes = self.plugins.cmdPreWithNodes("attachgdb", nodes)
        cmdSuccess, cmdOutput = control.attachGdb(nodes)
        if not cmdSuccess:
            self.exit_code = 1
        cmdOutput.printResults()
        self.plugins.cmdPostWithNodes("attachgdb", nodes)

        return False

    def do_cron(self, args):
        """- [enable|disable|?] | [--no-watch]

        This command has two modes of operation. Without arguments (or just
        ``--no-watch``), it performs a set of maintenance tasks, including
        the logging of various statistical information, expiring old log
        files, checking for dead hosts, and restarting nodes which terminated
        unexpectedly (the latter can be suppressed with the ``--no-watch``
        option if no auto-restart is desired). This mode is intended to be
        executed regularly via *cron*, as described in the installation
        instructions. While not intended for interactive use, no harm will be
        caused by executing the command manually: all the maintenance tasks
        will then just be performed one more time.

        The second mode is for interactive usage and determines if the regular
        tasks are indeed performed when ``broctl cron`` is executed. In other
        words, even with ``broctl cron`` in your crontab, you can still
        temporarily disable it by running ``cron disable``, and
        then later reenable with ``cron enable``. This can be helpful while
        working, e.g., on the BroControl configuration and ``cron`` would
        interfere with that. ``cron ?`` can be used to query the current state.
        """

        watch = True

        if args == "--no-watch":
            watch = False

        elif args:
            self.lock()

            if args == "enable":
                if self.plugins.cmdPre("cron", args, False):
                    config.Config._setState("cronenabled", "1")
                    util.output("cron enabled")
                self.plugins.cmdPost("cron", args, False)

            elif args == "disable":
                if self.plugins.cmdPre("cron", args, False):
                    config.Config._setState("cronenabled", "0")
                    util.output("cron disabled")
                self.plugins.cmdPost("cron", args, False)

            elif args == "?":
                if self.plugins.cmdPre("cron", args, False):
                    util.output("cron " + (config.Config.cronenabled == "0"  and "disabled" or "enabled"))
                self.plugins.cmdPost("cron", args, False)

            else:
                util.error("invalid cron argument")
                self.exit_code = 1

            return

        if self.plugins.cmdPre("cron", "", watch):
            cmdOutput = cron.doCron(watch)
            cmdOutput.printResults()
        self.plugins.cmdPost("cron", "", watch)

        return False

    @expose
    @lock_required
    def check(self, node_list=None):
        """- [<nodes>]

        Verifies a modified configuration in terms of syntactical correctness
        (most importantly correct syntax in policy scripts). This command
        should be executed for each configuration change *before*
        install_ is used to put the change into place.
        The ``check`` command uses the policy files as found in SitePolicyPath_
        to make sure they compile correctly. If they do, install_
        will then copy them over to an internal place from where the nodes
        will read them at the next start_. This approach
        ensures that new errors in a policy script will not affect currently
        running nodes, even when one or more of them needs to be restarted."""

        nodes = self.nodeArgs(node_list)

        nodes = self.plugins.cmdPreWithNodes("check", nodes)
        results = self.controller.checkConfigs(nodes)
        status = self.checkForFailure(results)
        self.plugins.cmdPostWithResults("check", results)

        return status

    @expose
    @lock_required
    def cleanup(self, node_list=None, all=False):
        """- [--all] [<nodes>]

        Clears the nodes' spool directories (if they are not running
        currently). This implies that their persistent state is flushed. Nodes
        that were crashed are reset into *stopped* state. If ``--all`` is
        specified, this command also removes the content of the node's
        TmpDir_, in particular deleteing any data
        potentially saved there for reference from previous crashes.
        Generally, if you want to reset the installation back into a clean
        state, you can first stop_ all nodes, then execute
        ``cleanup --all``, and finally start_ all nodes
        again."""

        cleantmp = all

        nodes = self.nodeArgs(node_list)

        nodes = self.plugins.cmdPreWithNodes("cleanup", nodes, cleantmp)
        cmdSuccess = self.controller.cleanup(nodes, cleantmp)
        self.plugins.cmdPostWithNodes("cleanup", nodes, cleantmp)

        return cmdSuccess

    def do_capstats(self, args):
        """- [<nodes>] [<interval>]

        Determines the current load on the network interfaces monitored by
        each of the given worker nodes. The load is measured over the
        specified interval (in seconds), or by default over 10 seconds. This
        command uses the :doc:`capstats<../../components/capstats/README>`
        tool, which is installed along with ``broctl``.

        (Note: When using a CFlow and the CFlow command line utility is
        installed as well, the ``capstats`` command can also query the device
        for port statistics. *TODO*: document how to set this up.)"""

        interval = 10
        args = args.split()

        try:
            interval = max(1, int(args[-1]))
            args = args[0:-1]
        except ValueError:
            pass
        except IndexError:
            pass

        node_list = " ".join(args)

        self.lock()
        nodes = self.nodeArgs(node_list)
        nodes = self.plugins.cmdPreWithNodes("capstats", nodes, interval)
        cmdSuccess, cmdOutput_cap, cmdOutput_cflow = control.capstats(nodes, interval)
        cmdOutput_cap.printResults()
        cmdOutput_cflow.printResults()
        self.plugins.cmdPostWithNodes("capstats", nodes, interval)

        return cmdSuccess

    def do_update(self, args):
        """- [<nodes>]

        After a change to Bro policy scripts, this command updates the Bro
        processes on the given nodes *while they are running* (i.e., without
        requiring a restart_). However, such dynamic
        updates work only for a *subset* of Bro's full configuration. The
        following changes can be applied on the fly:  The value of all
        const variables defined with the ``&redef`` attribute can be changed.
        More extensive script changes are not possible during runtime and
        always require a restart; if you change more than just the values of
        ``&redef``-able consts and still issue ``update``, the results are
        undefined and can lead to crashes. Also note that before running
        ``update``, you still need to do an install_ (preferably after
        check_), as otherwise ``update`` will not see the changes and it will
        resend the old configuration."""

        self.lock()
        nodes = self.nodeArgs(args)
        nodes = self.plugins.cmdPreWithNodes("update", nodes)
        results, cmdOutput = control.update(nodes)
        self.checkForFailure(results)
        cmdOutput.printResults()
        self.plugins.cmdPostWithResults("update", results)

        return False

    def do_df(self, args):
        """- [<nodes>]

        Reports the amount of disk space available on the nodes. Shows only
        paths relevant to the broctl installation."""

        self.lock()
        nodes = self.nodeHostArgs(args)
        nodes = self.plugins.cmdPreWithNodes("df", nodes)
        cmdSuccess, cmdOutput = control.df(nodes)
        cmdOutput.printResults()
        self.plugins.cmdPostWithNodes("df", nodes)

        return cmdSuccess

    def do_print(self, args):
        """- <id> [<nodes>]

        Reports the *current* live value of the given Bro script ID on all of
        the specified nodes (which obviously must be running). This can for
        example be useful to (1) check that policy scripts are working as
        expected, or (2) confirm that configuration changes have in fact been
        applied.  Note that IDs defined inside a Bro namespace must be
        prefixed with ``<namespace>::`` (e.g.,
        ``print HTTP::mime_types_extensions`` to print the corresponding
        table from ``file-ident.bro``)."""

        self.lock()
        args = args.split()
        try:
            id = args[0]

            nodes = self.nodeArgs(" ".join(args[1:]))
            nodes = self.plugins.cmdPreWithNodes("print", nodes, id)
            cmdSuccess, cmdOutput = control.printID(nodes, id)
            if not cmdSuccess:
                self.exit_code = 1
            cmdOutput.printResults()
            self.plugins.cmdPostWithNodes("print", nodes, id)
        except IndexError:
            self.syntax("no id given to print")

        return False

    def do_peerstatus(self, args):
        """- [<nodes>]

		Primarily for debugging, ``peerstatus`` reports statistics about the
        network connections cluster nodes are using to communicate with other
        nodes."""

        self.lock()
        nodes = self.nodeArgs(args)
        nodes = self.plugins.cmdPreWithNodes("peerstatus", nodes)
        cmdSuccess, cmdOutput = control.peerStatus(nodes)
        cmdOutput.printResults()
        self.plugins.cmdPostWithNodes("peerstatus", nodes)

        return cmdSuccess

    def do_netstats(self, args):
        """- [<nodes>]

		Queries each of the nodes for their current counts of captured and
        dropped packets."""

        if not args:
            if config.Config.nodes("standalone"):
                args = "standalone"
            else:
                args = "workers"

        self.lock()
        nodes = self.nodeArgs(args)
        nodes = self.plugins.cmdPreWithNodes("netstats", nodes)
        cmdSuccess, cmdOutput = control.netStats(nodes)
        cmdOutput.printResults()
        self.plugins.cmdPostWithNodes("netstats", nodes)

        return cmdSuccess

    @expose
    def execute(self, cmd):
        """- <command line>

		Executes the given Unix shell command line on all hosts configured to
        run at least one Bro instance. This is handy to quickly perform an
        action across all systems."""

        if self.plugins.cmdPre("exec", cmd):
            cmdSuccess = self.controller.executeCmd(self.config.hosts(), cmd)
        self.plugins.cmdPost("exec", cmd)

        return cmdSuccess

    def do_scripts(self, args):
        """- [-c] [<nodes>]

		Primarily for debugging Bro configurations, the ``scripts``
       	command lists all the Bro scripts loaded by each of the nodes in the
        order they will be parsed by the node at startup.
        If ``-c`` is given, the command operates as check_ does: it reads
        the policy files from their *original* location, not the copies
        installed by install_. The latter option is useful to check a
        not yet installed configuration."""

        check = False

        args = args.split()

        try:
            while args[0].startswith("-"):

                opt = args[0]

                if opt == "-c":
                    # Check non-installed policies.
                    check = True
                else:
                    self.syntax("unknown option %s" % args[0])
                    return

                args = args[1:]

        except IndexError:
            pass

        args = " ".join(args)

        self.lock()

        nodes = self.nodeArgs(args)

        nodes = self.plugins.cmdPreWithNodes("scripts", nodes, check)
        results, cmdOutput = control.listScripts(nodes, check)
        self.checkForFailure(results)
        cmdOutput.printResults()
        self.plugins.cmdPostWithNodes("scripts", nodes, check)

        return False

    def do_process(self, args):
        """- <trace> [options] [-- <scripts>]

        Runs Bro offline on a given trace file using the same configuration as
        when running live. It does, however, use the potentially
        not-yet-installed policy files in SitePolicyPath_ and disables log
        rotation. Additional Bro command line flags and scripts can
        be given (each argument after a ``--`` argument is interpreted as
        a script).

        Upon completion, the command prints a path where the log files can be
        found. Subsequent runs of this command may delete these logs.

        In cluster mode, Bro is run with *both* manager and worker scripts
        loaded into a single instance. While that doesn't fully reproduce the
        live setup, it is often sufficient for debugging analysis scripts.
        """
        options = []
        scripts = []
        trace = None
        in_scripts = False
        cmdSuccess = False

        for arg in args.split():

            if not trace:
                trace = arg
                continue

            if arg == "--":
                if in_scripts:
                    self.syntax("cannot parse arguments")
                    return

                in_scripts = True
                continue

            if not in_scripts:
                options += [arg]

            else:
                scripts += [arg]

        if not trace:
            self.syntax("no trace file given")
            return

        if self.plugins.cmdPre("process", trace, options, scripts):
            cmdSuccess, cmdOutput = control.processTrace(trace, options, scripts)
            cmdOutput.printResults()
        self.plugins.cmdPost("process", trace, options, scripts, cmdSuccess)

        if not cmdSuccess:
            self.exit_code = 1

    def completedefault(self, text, line, begidx, endidx):
        # Commands that take a "<nodes>" argument.
        nodes_cmds = ["capstats", "check", "cleanup", "df", "diag", "netstats", "print", "restart", "start", "status", "stop", "top", "update", "attachgdb", "peerstatus", "scripts"]

        args = line.split()

        if not args or args[0] not in nodes_cmds:
            return []

        nodes = ["manager", "workers", "proxies", "all"] + [n.name for n in Config.nodes()]

        return [n for n in nodes if n.startswith(text)]

    # Prints the command's docstring in a form suitable for direct inclusion
    # into the documentation.
    def printReference(self):
        print ".. Automatically generated. Do not edit."
        print

        cmds = []

        for i in self.__class__.__dict__:
            doc = self.__class__.__dict__[i].__doc__
            if i.startswith("do_") and doc:
                cmds += [(i[3:], doc)]

        cmds.sort()

        for (cmd, doc) in cmds:
            if doc.startswith("- "):
                # First line are arguments.
                doc = doc.split("\n")
                args = doc[0][2:]
                doc = "\n".join(doc[1:])
            else:
                args = ""

            if args:
                args = (" *%s*" % args)
            else:
                args = ""

            output = ""
            for line in doc.split("\n"):
                line = line.strip()
                output += "    " + line + "\n"

            output = output.strip()

            print
            print ".. _%s:\n\n*%s*%s\n    %s" % (cmd, cmd, args, output)
            print

    def do_help(self, args):
        """Prints a brief summary of all commands understood by the shell."""

        plugin_help = ""

        for (cmd, args, descr) in self.plugins.allCustomCommands():
            if not plugin_help:
                plugin_help += "\nCommands provided by plugins:\n\n"

            if args:
                cmd = "%s %s" % (cmd, args)

            plugin_help += "  %-32s - %s\n" % (cmd, descr)

        self.output(
"""
BroControl Version %s

  capstats [<nodes>] [<secs>]      - Report interface statistics with capstats
  check [<nodes>]                  - Check configuration before installing it
  cleanup [--all] [<nodes>]        - Delete working dirs (flush state) on nodes
  config                           - Print broctl configuration
  cron [--no-watch]                - Perform jobs intended to run from cron
  cron enable|disable|?            - Enable/disable \"cron\" jobs
  df [<nodes>]                     - Print nodes' current disk usage
  diag [<nodes>]                   - Output diagnostics for nodes
  exec <shell cmd>                 - Execute shell command on all hosts
  exit                             - Exit shell
  install                          - Update broctl installation/configuration
  netstats [<nodes>]               - Print nodes' current packet counters
  nodes                            - Print node configuration
  peerstatus [<nodes>]             - Print status of nodes' remote connections
  print <id> [<nodes>]             - Print values of script variable at nodes
  process <trace> [<op>] [-- <sc>] - Run Bro (with options and scripts) on trace
  quit                             - Exit shell
  restart [--clean] [<nodes>]      - Stop and then restart processing
  scripts [-c] [<nodes>]           - List the Bro scripts the nodes will load
  start [<nodes>]                  - Start processing
  status [<nodes>]                 - Summarize node status
  stop [<nodes>]                   - Stop processing
  top [<nodes>]                    - Show Bro processes ala top
  update [<nodes>]                 - Update configuration of nodes on the fly
  %s""" % (Version, plugin_help))
