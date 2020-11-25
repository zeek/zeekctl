# Tasks which are to be done on a regular basis from cron.
from __future__ import print_function
import io
import os
import time
import shutil

from ZeekControl import execute
from ZeekControl import node as node_mod

class CronUI:
    def __init__(self):
        self.buffer = None

    def info(self, txt):
        if self.buffer:
            self.buffer.write("%s\n" % txt)
        else:
            print(txt)
    error = info
    warn = info

    def buffer_output(self):
        self.buffer = io.StringIO()

    def get_buffered_output(self):
        buf = self.buffer.getvalue()
        self.buffer.close()
        self.buffer = None
        return buf


class CronTasks:
    def __init__(self, ui, config, controller, executor, pluginregistry):
        self.ui = ui
        self.config = config
        self.controller = controller
        self.executor = executor
        self.pluginregistry = pluginregistry

    def log_stats(self, interval):
        if not self.config.statslogenable:
            return

        nodes = self.config.nodes()
        top = self.controller.get_top_output(nodes)

        have_capstats = self.config.capstatspath
        capstats = []

        if have_capstats:
            capstats = self.controller.get_capstats_output(nodes, interval)

        t = time.time()

        try:
            with open(self.config.statslog, "a") as out:
                for (node, error, vals) in top:
                    if not error:
                        for (val, key) in sorted(vals.items()):
                            out.write("%s %s parent %s %s\n" % (t, node, val, key))
                    else:
                        out.write("%s %s error error %s\n" % (t, node, error))

                for (node, netif, success, vals) in capstats:
                    if not success:
                        out.write("%s %s error error %s\n" % (t, node, vals))
                        continue

                    for (key, val) in sorted(vals.items()):
                        out.write("%s %s interface %s %s\n" % (t, node, key, val))

                        if key == "pkts" and str(node) != "$total":
                            # Report if we don't see packets on an interface.
                            tag = "lastpkts-%s" % node.name

                            last = self.config.get_state(tag, default=-1.0)

                            if self.config.mailreceivingpackets:
                                if val == 0.0 and last != 0.0:
                                    self.ui.info("%s is not seeing any packets on interface %s" % (node.host, netif))

                                if val != 0.0 and last == 0.0:
                                    self.ui.info("%s is seeing packets again on interface %s" % (node.host, netif))

                            self.config.set_state(tag, val)

        except IOError as err:
            self.ui.error("failed to append to file: %s" % err)
            return

    def check_disk_space(self):
        minspace = self.config.mindiskspace
        if minspace == 0:
            return

        results = self.controller.df(self.config.hosts())
        for (node, _, dfs) in results.get_node_data():
            host = node.host

            for key, df in dfs.items():
                if key == "FAIL":
                    # A failure here is normally caused by a host that is down,
                    # so we don't need to output the error message.
                    continue

                fs = df.fs
                perc = df.percent
                key = ("disk-space-%s%s" % (host, fs.replace("/", "-")))

                if perc > 100 - minspace:
                    last = self.config.get_state(key, default=-1)
                    if last > 100 - minspace:
                        # Already reported.
                        continue

                    self.ui.warn("Disk space low on %s:%s - %.1f%% used." % (host, fs, perc))

                self.config.set_state(key, perc)

    def expire_logs(self):
        if self.config.logexpireminutes == 0 and self.config.statslogexpireinterval == 0:
            return

        if self.config.standalone:
            success, output = execute.run_localcmd(os.path.join(self.config.scriptsdir, "expire-logs"))

            if not success:
                self.ui.error("expire-logs failed\n%s" % output)
        else:
            nodes = self.config.hosts(tag=node_mod.logger_group())

            if not nodes:
                nodes = self.config.hosts(tag=node_mod.manager_group())

            expirelogs = os.path.join(self.config.scriptsdir, "expire-logs")
            cmds = [(node, expirelogs, []) for node in nodes]

            for (node, success, output) in self.executor.run_cmds(cmds):
                if not success:
                    self.ui.error("expire-logs failed for node %s\n" % node)
                    if output:
                        self.ui.error(output)


    def expire_crash(self):
        if self.config.crashexpireinterval == 0:
            return

        expirecrash = os.path.join(self.config.scriptsdir, "expire-crash")
        cmds = [(node, expirecrash, []) for node in self.config.hosts()]

        for (node, success, output) in self.executor.run_cmds(cmds):
            if not success:
                self.ui.error("expire-crash failed for node %s\n" % node)
                if output:
                    self.ui.error(output)

    def check_hosts(self):
        for host, status in self.executor.host_status():
            tag = "alive-%s" % host
            alive = status

            previous = self.config.get_state(tag)
            if previous is not None:
                if alive != previous:
                    self.pluginregistry.hostStatusChanged(host, alive)
                    if self.config.mailhostupdown:
                        up_or_down = "up" if alive else "down"
                        self.ui.info("host %s %s" % (host, up_or_down))

            self.config.set_state(tag, alive)

    def update_http_stats(self):
        if not self.config.statslogenable:
            return

        # Create meta file.
        if not os.path.exists(self.config.statsdir):
            try:
                os.makedirs(self.config.statsdir)
            except OSError as err:
                self.ui.error("failure creating directory in zeekctl option statsdir: %s" % err)
                return

            self.ui.info("creating directory for stats file: %s" % self.config.statsdir)

        metadat = os.path.join(self.config.statsdir, "meta.dat")
        try:
            with open(metadat, "w") as meta:
                for node in self.config.hosts():
                    meta.write("node %s %s %s\n" % (node, node.type, node.host))

                meta.write("time %s\n" % time.asctime())
                meta.write("version %s\n" % self.config.version)

                success, output = execute.run_localcmd("uname -a")
                if success and output:
                    # Note: "output" already has a '\n'
                    meta.write("os %s" % output)
                else:
                    meta.write("os <error>\n")

                success, output = execute.run_localcmd("hostname")
                if success and output:
                    # Note: "output" already has a '\n'
                    meta.write("host %s" % output)
                else:
                    meta.write("host <error>\n")

        except IOError as err:
            self.ui.error("failure creating file: %s" % err)
            return

        wwwdir = os.path.join(self.config.statsdir, "www")
        if not os.path.isdir(wwwdir):
            try:
                os.makedirs(wwwdir)
            except OSError as err:
                self.ui.error("failed to create directory: %s" % err)
                return

        # Update the WWW data
        statstocsv = os.path.join(self.config.scriptsdir, "stats-to-csv")

        success, output = execute.run_localcmd("%s %s %s %s" % (statstocsv, self.config.statslog, metadat, wwwdir))
        if success:
            shutil.copy(metadat, wwwdir)
        else:
            self.ui.error("error reported by stats-to-csv\n%s" % output)

        # Append the current stats.log in spool to the one in ${statsdir}
        dst = os.path.join(self.config.statsdir, os.path.basename(self.config.statslog))
        try:
            with open(self.config.statslog, "r") as fsrc:
                with open(dst, "a") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
        except IOError as err:
            self.ui.error("failed to append file: %s" % err)
            return

        os.unlink(self.config.statslog)


    def run_cron_cmd(self):
        # Run external command if we have one.
        if self.config.croncmd:
            success, output = execute.run_localcmd(self.config.croncmd)
            if not success:
                self.ui.error("failure running croncmd: %s" % self.config.croncmd)
