# Tasks which are to be done on a regular basis from cron.
import io
import os
import shutil
import time

from ZeekControl import execute
from ZeekControl import node as node_mod


class CronUI:
    def __init__(self):
        self.buffer = None

    def info(self, txt):
        if self.buffer:
            self.buffer.write(f"{txt}\n")
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
                for node, error, vals in top:
                    if not error:
                        for val, key in sorted(vals.items()):
                            out.write(f"{t} {node} parent {val} {key}\n")
                    else:
                        out.write(f"{t} {node} error error {error}\n")

                for node, netif, success, vals in capstats:
                    if not success:
                        out.write(f"{t} {node} error error {vals}\n")
                        continue

                    for key, val in sorted(vals.items()):
                        out.write(f"{t} {node} interface {key} {val}\n")

                        if key == "pkts" and str(node) != "$total":
                            # Report if we don't see packets on an interface.
                            tag = f"lastpkts-{node.name}"

                            last = self.config.get_state(tag, default=-1.0)

                            if self.config.mailreceivingpackets:
                                if val == 0.0 and last != 0.0:
                                    self.ui.info(
                                        f"{node.host} is not seeing any packets on interface {netif}"
                                    )

                                if val != 0.0 and last == 0.0:
                                    self.ui.info(
                                        f"{node.host} is seeing packets again on interface {netif}"
                                    )

                            self.config.set_state(tag, val)

        except OSError as err:
            self.ui.error(f"failed to append to file: {err}")
            return

    def check_disk_space(self):
        minspace = self.config.mindiskspace
        if minspace == 0:
            return

        results = self.controller.df(self.config.hosts())
        for node, _, dfs in results.get_node_data():
            host = node.host

            for key, df in dfs.items():
                if key == "FAIL":
                    # A failure here is normally caused by a host that is down,
                    # so we don't need to output the error message.
                    continue

                fs = df.fs
                perc = df.percent
                key = "disk-space-{}{}".format(host, fs.replace("/", "-"))

                if perc > 100 - minspace:
                    last = self.config.get_state(key, default=-1)
                    if last > 100 - minspace:
                        # Already reported.
                        continue

                    self.ui.warn(f"Disk space low on {host}:{fs} - {perc:.1f}% used.")

                self.config.set_state(key, perc)

    def expire_logs(self):
        if (
            self.config.logexpireminutes == 0
            and self.config.statslogexpireinterval == 0
        ):
            return

        if self.config.standalone:
            success, output = execute.run_localcmd(
                os.path.join(self.config.scriptsdir, "expire-logs")
            )

            if not success:
                self.ui.error(f"expire-logs failed\n{output}")
        else:
            nodes = self.config.hosts(tag=node_mod.logger_group())

            if not nodes:
                nodes = self.config.hosts(tag=node_mod.manager_group())

            expirelogs = os.path.join(self.config.scriptsdir, "expire-logs")
            cmds = [(node, expirelogs, []) for node in nodes]

            for node, success, output in self.executor.run_cmds(cmds):
                if not success:
                    self.ui.error(f"expire-logs failed for node {node}\n")
                    if output:
                        self.ui.error(output)

    def expire_crash(self):
        if self.config.crashexpireinterval == 0:
            return

        expirecrash = os.path.join(self.config.scriptsdir, "expire-crash")
        cmds = [(node, expirecrash, []) for node in self.config.hosts()]

        for node, success, output in self.executor.run_cmds(cmds):
            if not success:
                self.ui.error(f"expire-crash failed for node {node}\n")
                if output:
                    self.ui.error(output)

    def check_hosts(self):
        for host, status in self.executor.host_status():
            tag = f"alive-{host}"
            alive = status

            previous = self.config.get_state(tag)
            if previous is not None:
                if alive != previous:
                    self.pluginregistry.hostStatusChanged(host, alive)
                    if self.config.mailhostupdown:
                        up_or_down = "up" if alive else "down"
                        self.ui.info(f"host {host} {up_or_down}")

            self.config.set_state(tag, alive)

    def update_http_stats(self):
        if not self.config.statslogenable:
            return

        # Create meta file.
        if not os.path.exists(self.config.statsdir):
            try:
                os.makedirs(self.config.statsdir)
            except OSError as err:
                self.ui.error(
                    f"failure creating directory in zeekctl option statsdir: {err}"
                )
                return

            self.ui.info(f"creating directory for stats file: {self.config.statsdir}")

        metadat = os.path.join(self.config.statsdir, "meta.dat")
        try:
            with open(metadat, "w") as meta:
                for node in self.config.hosts():
                    meta.write(f"node {node} {node.type} {node.host}\n")

                meta.write(f"time {time.asctime()}\n")
                meta.write(f"version {self.config.version}\n")

                success, output = execute.run_localcmd("uname -a")
                if success and output:
                    # Note: "output" already has a '\n'
                    meta.write(f"os {output}")
                else:
                    meta.write("os <error>\n")

                success, output = execute.run_localcmd("hostname")
                if success and output:
                    # Note: "output" already has a '\n'
                    meta.write(f"host {output}")
                else:
                    meta.write("host <error>\n")

        except OSError as err:
            self.ui.error(f"failure creating file: {err}")
            return

        wwwdir = os.path.join(self.config.statsdir, "www")
        if not os.path.isdir(wwwdir):
            try:
                os.makedirs(wwwdir)
            except OSError as err:
                self.ui.error(f"failed to create directory: {err}")
                return

        # Update the WWW data
        statstocsv = os.path.join(self.config.scriptsdir, "stats-to-csv")

        success, output = execute.run_localcmd(
            f"{statstocsv} {self.config.statslog} {metadat} {wwwdir}"
        )
        if success:
            shutil.copy(metadat, wwwdir)
        else:
            self.ui.error(f"error reported by stats-to-csv\n{output}")

        # Append the current stats.log in spool to the one in ${statsdir}
        dst = os.path.join(self.config.statsdir, os.path.basename(self.config.statslog))
        try:
            with open(self.config.statslog) as fsrc:
                with open(dst, "a") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
        except OSError as err:
            self.ui.error(f"failed to append file: {err}")
            return

        os.unlink(self.config.statslog)

    def run_cron_cmd(self):
        # Run external command if we have one.
        if self.config.croncmd:
            success, output = execute.run_localcmd(self.config.croncmd)
            if not success:
                self.ui.error(f"failure running croncmd: {self.config.croncmd}")
