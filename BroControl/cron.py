# Tasks which are to be done on a regular basis from cron.
from __future__ import print_function
import os
import time
import shutil

from BroControl import execute
from BroControl import py3bro

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
        self.buffer = py3bro.io.StringIO()

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
        if self.config.statslogenable == "0":
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
                        for proc in vals:
                            parentchild = proc["proc"]
                            for (val, key) in proc.items():
                                if val != "proc":
                                    out.write("%s %s %s %s %s\n" % (t, node, parentchild, val, key))
                    else:
                        out.write("%s %s error error %s\n" % (t, node, error))

                for (node, netif, success, vals) in capstats:
                    if not success:
                        out.write("%s %s error error %s\n" % (t, node, vals))
                        continue

                    for (key, val) in vals.items():
                        out.write("%s %s interface %s %s\n" % (t, node, key, val))

                        if key == "pkts" and str(node) != "$total":
                            # Report if we don't see packets on an interface.
                            tag = "lastpkts-%s" % node.name.lower()

                            last = -1.0
                            if tag in self.config.state:
                                last = float(self.config.state[tag])

                            if float(val) == 0.0 and last != 0.0:
                                self.ui.info("%s is not seeing any packets on interface %s" % (node.host, netif))

                            if float(val) != 0.0 and last == 0.0:
                                self.ui.info("%s is seeing packets again on interface %s" % (node.host, netif))

                            self.config.set_state(tag, val)

        except IOError as err:
            self.ui.error("failed to append to file: %s" % err)
            return

    def check_disk_space(self):
        minspace = float(self.config.mindiskspace)
        if minspace == 0.0:
            return

        results = self.controller.df(self.config.hosts())
        for (node, _, dfs) in results.get_node_data():
            host = node.host

            for key, df in dfs.items():
                if key == "FAIL":
                    # A failure here is normally caused by a host that is down,
                    # so we don't need to output the error message.
                    continue

                fs = df[0]
                perc = df[4]
                key = ("disk-space-%s%s" % (host, fs.replace("/", "-"))).lower()

                if perc > 100 - minspace:
                    if key in self.config.state:
                        if float(self.config.state[key]) > 100 - minspace:
                            # Already reported.
                            continue

                    self.ui.warn("Disk space low on %s:%s - %.1f%% used." % (host, fs, perc))

                self.config.set_state(key, "%.1f" % perc)

    def expire_logs(self):
        if self.config.logexpireinterval == "0" and self.config.statslogexpireinterval == "0":
            return

        (success, output) = execute.run_localcmd(os.path.join(self.config.scriptsdir, "expire-logs"))

        if not success:
            self.ui.error("expire-logs failed\n")
            for line in output:
                self.ui.error(line)

    def check_hosts(self):
        for host, status in self.executor.host_status():
            tag = "alive-%s" % host
            alive = status and "1" or "0"

            if tag in self.config.state:
                previous = self.config.state[tag]

                if alive != previous:
                    self.pluginregistry.hostStatusChanged(host, alive == "1")
                    if self.config.mailhostupdown != "0":
                        self.ui.info("host %s %s" % (host, alive == "1" and "up" or "down"))

            self.config.set_state(tag, alive)

    def update_http_stats(self):
        if self.config.statslogenable == "0":
            return

        # Create meta file.
        if not os.path.exists(self.config.statsdir):
            try:
                os.makedirs(self.config.statsdir)
            except OSError as err:
                self.ui.error("failure creating directory in broctl option statsdir: %s" % err)
                return

            self.ui.info("creating directory for stats file: %s" % self.config.statsdir)

        metadat = os.path.join(self.config.statsdir, "meta.dat")
        try:
            with open(metadat, "w") as meta:
                for node in self.config.hosts():
                    meta.write("node %s %s %s\n" % (node, node.type, node.host))

                meta.write("time %s\n" % time.asctime())
                meta.write("version %s\n" % self.config.version)

                try:
                    meta.write("os %s\n" % execute.run_localcmd("uname -a")[1][0])
                except IndexError:
                    meta.write("os <error>\n")

                try:
                    meta.write("host %s\n" % execute.run_localcmd("hostname")[1][0])
                except IndexError:
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

        (success, output) = execute.run_localcmd("%s %s %s %s" % (statstocsv, self.config.statslog, metadat, wwwdir))
        if success:
            shutil.copy(metadat, wwwdir)
        else:
            self.ui.error("error reported by stats-to-csv")
            for line in output:
                self.ui.error(line)

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
            (success, output) = execute.run_localcmd(self.config.croncmd)
            if not success:
                self.ui.error("failure running croncmd: %s" % self.config.croncmd)

