#! /usr/bin/env python
#
# The BroControl interactive shell.

import os
import sys
import time

from BroControl import util
from BroControl import config
from BroControl import execute
from BroControl import install
from BroControl import control
from BroControl import cron
from BroControl import plugin
from BroControl import version
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
    def wrapper(self, *args, **kwargs):
        self.lock()
        try:
            return func(self, *args, **kwargs)
        finally:
            self.unlock()
    wrapper.lock_required = True
    return wrapper

class BroCtl(object):
    def __init__(self, basedir=version.BROBASE, ui=TermUI(), state=None):
        self.ui = ui
        self.BroBase = basedir

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
        if isinstance(args, basestring):
            args = args.split()

        for arg in args:
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

        if isinstance(args, basestring):
            args = args.split()

        for arg in args:
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
            raise RuntimeError("Unable to get lock")

        statestatus = self.config.readState(self.ui)
        if not statestatus:
            raise RuntimeError("Unable to get state")

    def unlock(self):
        util.unlock(self.ui)

    def checkForFailure(self, results):
        return not util.nodeFailed(results)

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
    def restart(self, clean=False, node_list=None):
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
        if not success:
            return False

        if clean:
            self.output("cleaning up ...")
            success = self.cleanup(node_list)
            if not success:
                return False

            self.output("checking configurations ...")
            success = self.check(node_list)
            if not success:
                return False

            self.output("installing ...")
            success = self.install()
            if not success:
                return False

        self.output("starting ...")
        success = self.start(node_list)

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

    def top(self, node_list=None):
        """- [<nodes>]

        For each of the nodes, prints the status of the two Bro
        processes (parent process and child process) in a *top*-like
        format, including CPU usage and memory consumption. If
        executed interactively, the display is updated frequently
        until key ``q`` is pressed. If invoked non-interactively, the
        status is printed only once."""

        nodes = self.nodeArgs(node_list)

        nodes = self.plugins.cmdPreWithNodes("top", nodes)
        results = self.controller.top(nodes)
        self.plugins.cmdPostWithNodes("top", nodes)

        return results

    def diag(self, node_list=None):
        """- [<nodes>]

        If a node has terminated unexpectedly, this command prints a (somewhat
        cryptic) summary of its final state including excerpts of any
        stdout/stderr output, resource usage, and also a stack backtrace if a
        core dump is found. The same information is sent out via mail when a
        node is found to have crashed (the "crash report"). While the
        information is mainly intended for debugging, it can also help to find
        misconfigurations (which are usually, but not always, caught by the
        check_ command)."""

        nodes = self.nodeArgs(node_list)

        nodes = self.plugins.cmdPreWithNodes("diag", nodes)

        results = []
        for h in nodes:
            success, output = self.controller.crashDiag(h)
            results.append((h.name, success, output))

        self.plugins.cmdPostWithNodes("diag", nodes)

        return results

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

    def cron(self, watch=True):
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

        if self.plugins.cmdPre("cron", "", watch):
            cmdOutput = cron.doCron(watch)
            cmdOutput.printResults()
        self.plugins.cmdPost("cron", "", watch)

        return True

    def cronenabled(self):
        if self.plugins.cmdPre("cron", "?", False):
            if not self.config.hasAttr("cronenabled"):
                self.config._setState("cronenabled", True)
            self.output("cron " + (self.config.cronenabled and "enabled" or "disabled"))
        self.plugins.cmdPost("cron", "?", False)
        return True

    def setcronenabled(self, enable=True):
        if enable:
            if self.plugins.cmdPre("cron", "enable", False):
                self.config._setState("cronenabled", True)
                self.output("cron enabled")
            self.plugins.cmdPost("cron", "enable", False)
        else:
            if self.plugins.cmdPre("cron", "disable", False):
                self.config._setState("cronenabled", False)
                self.output("cron disabled")
            self.plugins.cmdPost("cron", "disable", False)

        return True

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
        self.plugins.cmdPostWithResults("check", results)

        return results

    @expose
    @lock_required
    def cleanup(self, all=False, node_list=None):
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
        results = self.controller.cleanup(nodes, cleantmp)
        self.plugins.cmdPostWithNodes("cleanup", nodes, cleantmp)

        return results

    def capstats(self, interval=10, node_list=None):
        """- [<nodes>] [<interval>]

        Determines the current load on the network interfaces monitored by
        each of the given worker nodes. The load is measured over the
        specified interval (in seconds), or by default over 10 seconds. This
        command uses the :doc:`capstats<../../components/capstats/README>`
        tool, which is installed along with ``broctl``.

        (Note: When using a CFlow and the CFlow command line utility is
        installed as well, the ``capstats`` command can also query the device
        for port statistics. *TODO*: document how to set this up.)"""

        nodes = self.nodeArgs(node_list)
        nodes = self.plugins.cmdPreWithNodes("capstats", nodes, interval)
        results = self.controller.capstats(nodes, interval)
        self.plugins.cmdPostWithNodes("capstats", nodes, interval)

        return results

    def update(self, node_list=None):
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

        nodes = self.nodeArgs(node_list)
        nodes = self.plugins.cmdPreWithNodes("update", nodes)
        results = self.controller.update(nodes)
        status = self.checkForFailure(results)
        self.plugins.cmdPostWithResults("update", results)

        return status

    def df(self, node_list=None):
        """- [<nodes>]

        Reports the amount of disk space available on the nodes. Shows only
        paths relevant to the broctl installation."""

        nodes = self.nodeHostArgs(node_list)
        nodes = self.plugins.cmdPreWithNodes("df", nodes)
        results = self.controller.df(nodes)
        self.plugins.cmdPostWithNodes("df", nodes)

        return results

    def printid(self, id, node_list=None):
        """- <id> [<nodes>]

        Reports the *current* live value of the given Bro script ID on all of
        the specified nodes (which obviously must be running). This can for
        example be useful to (1) check that policy scripts are working as
        expected, or (2) confirm that configuration changes have in fact been
        applied.  Note that IDs defined inside a Bro namespace must be
        prefixed with ``<namespace>::`` (e.g.,
        ``print HTTP::mime_types_extensions`` to print the corresponding
        table from ``file-ident.bro``)."""

        nodes = self.nodeArgs(node_list)
        nodes = self.plugins.cmdPreWithNodes("print", nodes, id)
        results = self.controller.printID(nodes, id)
        self.plugins.cmdPostWithNodes("print", nodes, id)

        return results

    def peerstatus(self, node_list=None):
        """- [<nodes>]

		Primarily for debugging, ``peerstatus`` reports statistics about the
        network connections cluster nodes are using to communicate with other
        nodes."""

        nodes = self.nodeArgs(node_list)
        nodes = self.plugins.cmdPreWithNodes("peerstatus", nodes)
        results = self.controller.peerStatus(nodes)
        self.plugins.cmdPostWithNodes("peerstatus", nodes)

        return results

    def netstats(self, node_list=None):
        """- [<nodes>]

		Queries each of the nodes for their current counts of captured and
        dropped packets."""

        if not node_list:
            if self.config.nodes("standalone"):
                node_list = "standalone"
            else:
                node_list = "workers"

        nodes = self.nodeArgs(node_list)
        nodes = self.plugins.cmdPreWithNodes("netstats", nodes)
        results = self.controller.netStats(nodes)
        self.plugins.cmdPostWithNodes("netstats", nodes)

        return results

    @expose
    def execute(self, cmd):
        """- <command line>

		Executes the given Unix shell command line on all hosts configured to
        run at least one Bro instance. This is handy to quickly perform an
        action across all systems."""

        results = []
        if self.plugins.cmdPre("exec", cmd):
            results = self.controller.executeCmd(self.config.hosts(), cmd)
        self.plugins.cmdPost("exec", cmd)

        return results

    def scripts(self, check=False, node_list=None):
        """- [-c] [<nodes>]

		Primarily for debugging Bro configurations, the ``scripts``
       	command lists all the Bro scripts loaded by each of the nodes in the
        order they will be parsed by the node at startup.
        If ``-c`` is given, the command operates as check_ does: it reads
        the policy files from their *original* location, not the copies
        installed by install_. The latter option is useful to check a
        not yet installed configuration."""

        nodes = self.nodeArgs(node_list)

        nodes = self.plugins.cmdPreWithNodes("scripts", nodes, check)
        results = self.controller.listScripts(nodes, check)
        self.plugins.cmdPostWithNodes("scripts", nodes, check)

        return results

    def process(self, trace, options, scripts):
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

        if self.plugins.cmdPre("process", trace, options, scripts):
            results = self.controller.processTrace(trace, options, scripts)
        self.plugins.cmdPost("process", trace, options, scripts, results["success"])

        return results


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

