# The ZeekControl interactive shell.

from __future__ import print_function
import os
import sys
import logging

from ZeekControl import lock
from ZeekControl import config
from ZeekControl import cmdresult
from ZeekControl import execute
from ZeekControl import control
from ZeekControl import version
from ZeekControl import pluginreg
from ZeekControl import node as node_mod
from ZeekControl.exceptions import *

class TermUI:
    def info(self, txt):
        print(txt)

    def error(self, txt):
        print(txt, file=sys.stderr)
    warn = error


class NullHandler(logging.Handler):
    def emit(self, record):
        pass


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

def lock_required_silent(func):
    def wrapper(self, *args, **kwargs):
        self.lock(showwait=False)
        try:
            return func(self, *args, **kwargs)
        finally:
            self.unlock()
    wrapper.lock_required = True
    return wrapper

def check_config(func):
    def wrapper(self, *args, **kwargs):
        if config.Config.is_cfg_changed():
            self.ui.warn('Configuration has changed. Run the "deploy" command.')
        return func(self, *args, **kwargs)

    return wrapper

class ZeekCtl(object):
    def __init__(self, basedir=version.ZEEKBASE, libdir=version.LIBDIR, cfgfile=version.CFGFILE,
                 zeekscriptdir=version.ZEEKSCRIPTDIR, ui=TermUI(), state=None):
        self.ui = ui
        self.zeekbase = basedir
        self.libdir = libdir

        self.config = config.Configuration(self.zeekbase, self.libdir, cfgfile, zeekscriptdir, self.ui, state)

        # Remove all log handlers (set by any previous calls to logging.*)
        logging.getLogger().handlers = []

        if self.config.debug:
            # Add a log handler that logs to a file.
            try:
                logging.basicConfig(filename=self.config.debuglog,
                            format="%(asctime)s [%(module)s] %(message)s",
                            datefmt=self.config.timefmt,
                            level=logging.DEBUG)
            except IOError as err:
                raise RuntimeEnvironmentError("%s\nCheck if the user running ZeekControl has write access to the debug log file." % err)
        else:
            # Add a log handler that does nothing.
            h = NullHandler()
            logging.getLogger().addHandler(h)

        self.executor = execute.Executor(self.config)
        self.plugins = pluginreg.PluginRegistry()
        self.setup()
        self.controller = control.Controller(self.config, self.ui, self.executor, self.plugins)

    def setup(self):
        plugindirs = self.config.sitepluginpath.split(":")
        plugindirs.append(self.config.plugindir)
        plugindirs.append(self.config.pluginzeekdir)

        for pdir in plugindirs:
            if pdir:
                self.plugins.addDir(pdir)

        self.plugins.loadPlugins(self.ui, self.executor)
        self.plugins.initPluginOptions()
        self.plugins.addNodeKeys()
        self.config.initPostPlugins()
        self.plugins.initPlugins(self.ui)
        self.plugins.initPluginCmds()
        os.chdir(self.config.zeekbase)
        if self.config.get_state("cronenabled") is None:
            self.config.set_state("cronenabled", True)

    def reload_cfg(self):
        self.config.reload_cfg()

        if self.config.debug:
            if isinstance(logging.getLogger().handlers[0], NullHandler):
                # Remove the null handler and configure logging to a file.
                logging.getLogger().handlers = []
                logging.basicConfig(filename=self.config.debuglog,
                            format="%(asctime)s [%(module)s] %(message)s",
                            datefmt=self.config.timefmt,
                            level=logging.DEBUG)

            # Re-enable all log levels.
            logging.disable(logging.NOTSET)
        else:
            # Disable logging to all log levels that we use.
            logging.disable(logging.CRITICAL)

        self.executor.finish()
        self.plugins.initPluginOptions()
        self.config.initPostPlugins()
        self.plugins.initPlugins(self.ui)
        self.plugins.initPluginCmds()

    def finish(self):
        self.executor.finish()
        self.plugins.finishPlugins()

    def warn_zeekctl_install(self):
        self.config.warn_zeekctl_install()

    # Turns node name arguments into a list of nodes.  If "get_hosts" is True,
    # then only one node per host is chosen.  If "get_types" is True, then
    # only one node per node type (manager, proxy, etc.) is chosen.
    def node_args(self, args=None, get_hosts=False, get_types=False):
        nodes = []

        if args:
            for arg in args.split():
                nodelist = self.config.nodes(arg)
                if not nodelist:
                    raise InvalidNodeError("unknown node '%s'" % arg)

                nodes += nodelist

            # Remove duplicate nodes
            newlist = list(set(nodes))
            if len(newlist) != len(nodes):
                nodes = newlist
        else:
            # Get all nodes.
            nodes = self.config.nodes()

        # Sort the list so that it doesn't depend on initial order of arguments
        nodes.sort(key=node_mod.sortnode)

        if get_hosts:
            hosts = {}
            hostnodes = []
            for node in nodes:
                if node.host not in hosts:
                    hosts[node.host] = 1
                    hostnodes.append(node)

            nodes = hostnodes

        if get_types:
            types = {}
            typenodes = []
            for node in nodes:
                if node.type not in types:
                    types[node.type] = 1
                    typenodes.append(node)

            nodes = typenodes

        return nodes

    def lock(self, showwait=True):
        lockstatus = lock.lock(self.ui, showwait)
        if not lockstatus:
            raise LockError("Unable to get lock")

        self.config.read_state()

    def unlock(self):
        lock.unlock(self.ui)

    def node_names(self):
        return [ n.name for n in self.config.nodes() ]

    def node_groups(self):
        return node_mod.node_groups()

    @expose
    @check_config
    def nodes(self):
        results = cmdresult.CmdResult()

        if self.plugins.cmdPre("nodes"):
            for n in self.config.nodes():
                results.set_node_data(n, True, n.to_dict())
        else:
            results.ok = False

        self.plugins.cmdPost("nodes")

        return results

    @expose
    @check_config
    def get_config(self):
        results = cmdresult.CmdResult()

        if self.plugins.cmdPre("config"):
            results.keyval = self.config.options()
        else:
            results.ok = False

        self.plugins.cmdPost("config")
        return results

    @expose
    @check_config
    @lock_required
    def install(self, local=False):
        if self.plugins.cmdPre("install"):
            results = self.controller.install(local)
        else:
            results = cmdresult.CmdResult(ok=False)

        self.plugins.cmdPost("install")
        return results

    @expose
    @check_config
    @lock_required
    def start(self, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("start", nodes)
        results = self.controller.start(nodes)
        self.plugins.cmdPostWithResults("start", results.get_node_data())

        return results

    @expose
    @check_config
    @lock_required
    def stop(self, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("stop", nodes)
        results = self.controller.stop(nodes)
        self.plugins.cmdPostWithResults("stop", results.get_node_data())

        return results

    @expose
    @check_config
    @lock_required
    def restart(self, clean=False, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("restart", nodes, clean)

        self.ui.info("stopping ...")
        results = self.stop(node_list)
        if not results.ok:
            return results

        if clean:
            self.ui.info("cleaning up ...")
            results = self.cleanup(node_list=node_list)
            if not results.ok:
                return results

            self.ui.info("checking configurations ...")
            results = self.check(node_list)
            if not results.ok:
                return results

            self.ui.info("installing ...")
            results = self.install()
            if not results.ok:
                return results

        self.ui.info("starting ...")
        results = self.start(node_list)

        self.plugins.cmdPostWithNodes("restart", nodes)
        return results

    @expose
    @lock_required
    def deploy(self):
        if not self.plugins.cmdPre("deploy"):
            results = cmdresult.CmdResult(ok=False)
            return results

        if self.config.is_cfg_changed():
            self.ui.info("Reloading zeekctl configuration ...")
            self.reload_cfg()

        self.ui.info("checking configurations ...")
        results = self.check(check_node_types=True)
        if not results.ok:
            for (node, success, output) in results.get_node_output():
                if not success:
                    self.ui.info("%s scripts failed." % node)
                    self.ui.info(output)

            return results

        self.ui.info("installing ...")
        results = self.install()
        if not results.ok:
            return results

        self.ui.info("stopping ...")
        results = self.stop()
        if not results.ok:
            return results

        self.ui.info("starting ...")
        results = self.start()

        self.plugins.cmdPost("deploy")
        return results

    @expose
    @check_config
    @lock_required
    def status(self, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("status", nodes)
        results = self.controller.status(nodes)
        self.plugins.cmdPostWithNodes("status", nodes)
        return results

    @expose
    @lock_required
    def top(self, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("top", nodes)
        results = self.controller.top(nodes)
        self.plugins.cmdPostWithNodes("top", nodes)

        return results

    @expose
    @check_config
    @lock_required
    def diag(self, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("diag", nodes)
        results = self.controller.diag(nodes)
        self.plugins.cmdPostWithNodes("diag", nodes)

        return results

    @expose
    @lock_required_silent
    def cron(self, watch=True):
        if self.plugins.cmdPre("cron", "", watch):
            self.controller.cron(watch)
        self.plugins.cmdPost("cron", "", watch)

        return True

    @expose
    @check_config
    @lock_required
    def cronenabled(self):
        results = False
        if self.plugins.cmdPre("cron", "?", False):
            results = self.config.cronenabled
        self.plugins.cmdPost("cron", "?", False)
        return results

    @expose
    @check_config
    @lock_required
    def setcronenabled(self, enable=True):
        if enable:
            if self.plugins.cmdPre("cron", "enable", False):
                self.config.set_state("cronenabled", True)
                self.ui.info("cron enabled")
            self.plugins.cmdPost("cron", "enable", False)
        else:
            if self.plugins.cmdPre("cron", "disable", False):
                self.config.set_state("cronenabled", False)
                self.ui.info("cron disabled")
            self.plugins.cmdPost("cron", "disable", False)

        return True

    @expose
    @check_config
    @lock_required
    def check(self, node_list=None, check_node_types=False):
        nodes = self.node_args(node_list, get_types=check_node_types)

        nodes = self.plugins.cmdPreWithNodes("check", nodes)
        results = self.controller.check(nodes)
        self.plugins.cmdPostWithResults("check", results.get_node_data())

        return results

    @expose
    @check_config
    @lock_required
    def cleanup(self, cleantmp=False, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("cleanup", nodes, cleantmp)
        results = self.controller.cleanup(nodes, cleantmp)
        self.plugins.cmdPostWithNodes("cleanup", nodes, cleantmp)

        return results

    @expose
    @check_config
    @lock_required
    def capstats(self, interval=10, node_list=None):
        nodes = self.node_args(node_list)
        nodes = self.plugins.cmdPreWithNodes("capstats", nodes, interval)
        results = self.controller.capstats(nodes, interval)
        self.plugins.cmdPostWithNodes("capstats", nodes, interval)

        return results

    @expose
    @check_config
    @lock_required
    def df(self, node_list=None):
        nodes = self.node_args(node_list, get_hosts=True)
        nodes = self.plugins.cmdPreWithNodes("df", nodes)
        results = self.controller.df(nodes)
        self.plugins.cmdPostWithNodes("df", nodes)

        return results

    @expose
    @check_config
    @lock_required
    def print_id(self, id, node_list=None):
        nodes = self.node_args(node_list)
        nodes = self.plugins.cmdPreWithNodes("print", nodes, id)
        results = self.controller.print_id(nodes, id)
        self.plugins.cmdPostWithNodes("print", nodes, id)

        return results

    @expose
    @check_config
    @lock_required
    def peerstatus(self, node_list=None):
        nodes = self.node_args(node_list)
        nodes = self.plugins.cmdPreWithNodes("peerstatus", nodes)
        results = self.controller.peerstatus(nodes)
        self.plugins.cmdPostWithNodes("peerstatus", nodes)

        return results

    @expose
    @check_config
    @lock_required
    def netstats(self, node_list=None):
        if not node_list:
            node_list = None
            if not self.config.standalone:
                node_list = node_mod.worker_group()

        nodes = self.node_args(node_list)
        nodes = self.plugins.cmdPreWithNodes("netstats", nodes)
        results = self.controller.netstats(nodes)
        self.plugins.cmdPostWithNodes("netstats", nodes)

        return results

    @expose
    @check_config
    def execute(self, cmd):
        nodes = self.node_args(get_hosts=True)

        if self.plugins.cmdPre("exec", cmd):
            results = self.controller.execute_cmd(nodes, cmd)
        else:
            results = cmdresult.CmdResult(ok=False)

        self.plugins.cmdPost("exec", cmd)

        return results

    @expose
    @check_config
    @lock_required
    def scripts(self, check=False, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("scripts", nodes, check)
        results = self.controller.scripts(nodes, check)
        self.plugins.cmdPostWithNodes("scripts", nodes, check)

        return results

    @expose
    @check_config
    @lock_required
    def process(self, trace, options, scripts):
        if self.plugins.cmdPre("process", trace, options, scripts):
            results = self.controller.process(trace, options, scripts)
        else:
            results = cmdresult.CmdResult(ok=False)

        self.plugins.cmdPost("process", trace, options, scripts, results.ok)

        return results

    @expose
    @check_config
    @lock_required
    def plugincmd(self, cmd, args):
        return self.plugins.runCustomCommand(cmd, args, self.ui)

