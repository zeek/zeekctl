# The BroControl interactive shell.

from __future__ import print_function
import os
import sys
import logging

from BroControl import util
from BroControl import config
from BroControl import execute
from BroControl import control
from BroControl import version
from BroControl import pluginreg

class InvalidNodeError(Exception):
    pass

class TermUI:
    def output(self, txt):
        print(txt)
    info = output
    debug = output

    def error(self, txt):
        print(txt, file=sys.stderr)
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

def lock_required_silent(func):
    def wrapper(self, *args, **kwargs):
        self.lock(showwait=False)
        try:
            return func(self, *args, **kwargs)
        finally:
            self.unlock()
    wrapper.lock_required = True
    return wrapper

class BroCtl(object):
    def __init__(self, basedir=version.BROBASE, cfgfile=version.CFGFILE, ui=TermUI(), state=None):
        self.ui = ui
        self.brobase = basedir

        self.localaddrs = execute.get_local_addrs(self.ui)
        self.config = config.Configuration(self.brobase, cfgfile, self.ui, self.localaddrs, state)

        if self.config.debug != "0":
            # clear the log handlers (set by previous calls to logging.*)
            logging.getLogger().handlers = []
            logging.basicConfig(filename=self.config.debuglog,
                                format="%(asctime)s [%(module)s] %(message)s",
                                datefmt=self.config.timefmt,
                                level=logging.DEBUG)

        self.executor = execute.Executor(self.ui, self.localaddrs, self.config.helperdir)
        self.plugins = pluginreg.PluginRegistry()
        self.setup()
        self.controller = control.Controller(self.config, self.ui, self.executor, self.plugins)

    def setup(self):
        for pdir in self.config.sitepluginpath.split(":") + [self.config.plugindir]:
            if pdir:
                self.plugins.addDir(pdir)

        self.plugins.loadPlugins(self.ui, self.executor)
        self.plugins.addNodeKeys()
        self.config.initPostPlugins()
        self.plugins.initPlugins()
        util.enable_signals()
        os.chdir(self.config.brobase)

    def warn_broctl_install(self):
        self.config.warn_broctl_install()

    # Turns nodes arguments into a list of node names.
    def node_args(self, args=None):
        if not args:
            args = "all"

        nodes = []

        for arg in args.split():
            nodelist = self.config.nodes(arg)
            if not nodelist and arg != "all":
                raise InvalidNodeError("unknown node '%s'" % arg)

            nodes += nodelist

        return nodes

    # Turns node name arguments into a list of nodes.  The result is a subset
    # of a similar call to node_args() but here only one node is chosen for
    # each host.
    def node_host_args(self, args=None):
        if not args:
            args = "all"

        hosts = {}
        nodes = []

        for arg in args.split():
            nodelist = self.config.hosts(arg)
            if not nodelist and arg != "all":
                raise InvalidNodeError("unknown node '%s'" % arg)

            for node in nodelist:
                if node.host not in hosts:
                    hosts[node.host] = 1
                    nodes.append(node)

        return nodes

    def output(self, text):
        self.ui.info(text)

    def error(self, text):
        self.ui.error(text)

    def syntax(self, args):
        self.error("Syntax error: %s" % args)

    def lock(self, showwait=True):
        lockstatus = util.lock(self.ui, showwait)
        if not lockstatus:
            raise RuntimeError("Unable to get lock")

        self.config.read_state()

    def unlock(self):
        util.unlock(self.ui)

    @expose
    def nodes(self):
        nodes = []
        if self.plugins.cmdPre("nodes"):
            nodes = [ n.describe() for n in self.config.nodes() ]
        self.plugins.cmdPost("nodes")
        return nodes

    @expose
    def get_config(self):
        configlist = []
        if self.plugins.cmdPre("config"):
            configlist = self.config.options()
        self.plugins.cmdPost("config")
        return configlist

    @expose
    @lock_required
    def install(self, local=False):
        results = None
        if self.plugins.cmdPre("install"):
            results = self.controller.install(local)

        self.plugins.cmdPost("install")
        return results

    @expose
    @lock_required
    def start(self, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("start", nodes)
        results = self.controller.start(nodes)
        self.plugins.cmdPostWithResults("start", results.get_node_data())

        return results

    @expose
    @lock_required
    def stop(self, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("stop", nodes)
        results = self.controller.stop(nodes)
        self.plugins.cmdPostWithResults("stop", results.get_node_data())

        return results

    @expose
    @lock_required
    def restart(self, clean=False, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("restart", nodes, clean)
        args = " ".join([ str(n) for n in nodes ])

        self.output("stopping ...")
        results = self.stop(node_list)
        if not results.ok:
            return results

        if clean:
            self.output("cleaning up ...")
            results = self.cleanup(node_list)
            if not results.ok:
                return results

            self.output("checking configurations ...")
            results = self.check(node_list)
            if not results.ok:
                return results

            self.output("installing ...")
            results = self.install()
            if not results.ok:
                return results

        self.output("starting ...")
        results = self.start(node_list)

        self.plugins.cmdPostWithNodes("restart", nodes)
        return results

    @expose
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
    @lock_required
    def cronenabled(self):
        results = False
        if self.plugins.cmdPre("cron", "?", False):
            if not self.config.has_attr("cronenabled"):
                self.config.set_state("cronenabled", True)
            results = self.config.cronenabled
        self.plugins.cmdPost("cron", "?", False)
        return results

    @expose
    @lock_required
    def setcronenabled(self, enable=True):
        if enable:
            if self.plugins.cmdPre("cron", "enable", False):
                self.config.set_state("cronenabled", True)
                self.output("cron enabled")
            self.plugins.cmdPost("cron", "enable", False)
        else:
            if self.plugins.cmdPre("cron", "disable", False):
                self.config.set_state("cronenabled", False)
                self.output("cron disabled")
            self.plugins.cmdPost("cron", "disable", False)

        return True

    @expose
    @lock_required
    def check(self, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("check", nodes)
        results = self.controller.check(nodes)
        self.plugins.cmdPostWithResults("check", results.get_node_data())

        return results

    @expose
    @lock_required
    def cleanup(self, cleantmp=False, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("cleanup", nodes, cleantmp)
        results = self.controller.cleanup(nodes, cleantmp)
        self.plugins.cmdPostWithNodes("cleanup", nodes, cleantmp)

        return results

    @expose
    @lock_required
    def capstats(self, interval=10, node_list=None):
        nodes = self.node_args(node_list)
        nodes = self.plugins.cmdPreWithNodes("capstats", nodes, interval)
        results = self.controller.capstats(nodes, interval)
        self.plugins.cmdPostWithNodes("capstats", nodes, interval)

        return results

    @expose
    @lock_required
    def update(self, node_list=None):
        nodes = self.node_args(node_list)
        nodes = self.plugins.cmdPreWithNodes("update", nodes)
        results = self.controller.update(nodes)
        self.plugins.cmdPostWithResults("update", results.get_node_data())

        return results

    @expose
    @lock_required
    def df(self, node_list=None):
        nodes = self.node_host_args(node_list)
        nodes = self.plugins.cmdPreWithNodes("df", nodes)
        results = self.controller.df(nodes)
        self.plugins.cmdPostWithNodes("df", nodes)

        return results

    @expose
    @lock_required
    def print_id(self, id, node_list=None):
        nodes = self.node_args(node_list)
        nodes = self.plugins.cmdPreWithNodes("print", nodes, id)
        results = self.controller.print_id(nodes, id)
        self.plugins.cmdPostWithNodes("print", nodes, id)

        return results

    @expose
    @lock_required
    def peerstatus(self, node_list=None):
        nodes = self.node_args(node_list)
        nodes = self.plugins.cmdPreWithNodes("peerstatus", nodes)
        results = self.controller.peerstatus(nodes)
        self.plugins.cmdPostWithNodes("peerstatus", nodes)

        return results

    @expose
    @lock_required
    def netstats(self, node_list=None):
        if not node_list:
            if self.config.nodes("standalone"):
                node_list = "standalone"
            else:
                node_list = "workers"

        nodes = self.node_args(node_list)
        nodes = self.plugins.cmdPreWithNodes("netstats", nodes)
        results = self.controller.netstats(nodes)
        self.plugins.cmdPostWithNodes("netstats", nodes)

        return results

    @expose
    def execute(self, cmd):
        results = None
        if self.plugins.cmdPre("exec", cmd):
            results = self.controller.execute_cmd(self.config.hosts(), cmd)
        self.plugins.cmdPost("exec", cmd)

        return results

    @expose
    @lock_required
    def scripts(self, check=False, node_list=None):
        nodes = self.node_args(node_list)

        nodes = self.plugins.cmdPreWithNodes("scripts", nodes, check)
        results = self.controller.scripts(nodes, check)
        self.plugins.cmdPostWithNodes("scripts", nodes, check)

        return results

    @expose
    @lock_required
    def process(self, trace, options, scripts):
        results = None
        if self.plugins.cmdPre("process", trace, options, scripts):
            results = self.controller.process(trace, options, scripts)
        self.plugins.cmdPost("process", trace, options, scripts, results.ok)

        return results

