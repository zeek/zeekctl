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
        pass

    def output(self, txt):
        if self.buffer:
            self.buffer.write(txt)
        else:
            print(txt)
    info = output
    debug = output
    error = output
    warn = output

    def bufferOutput(self):
        self.buffer = py3bro.io.StringIO()

    def getBufferedOutput(self):
        buf = self.buffer.getvalue()
        self.buffer.close()
        self.buffer = None
        return buf


class CronTasks:
    def __init__(self, ui, config, controller):
        self.ui = ui
        self.config = config
        self.controller = controller

    def logStats(self, interval):
        nodes = self.config.nodes()
        top = self.controller.getTopOutput(nodes)

        have_cflow = self.config.cflowaddress and self.config.cflowuser and self.config.cflowpassword
        have_capstats = self.config.capstatspath
        cflow_start = cflow_end = None
        capstats = []
        cflow_rates = []

        if have_cflow:
            cflow_start = self.controller.getCFlowStatus()

        if have_capstats:
            capstats = self.controller.getCapstatsOutput(nodes, interval)

        elif have_cflow:
            time.sleep(interval)

        if have_cflow:
            cflow_end = self.controller.getCFlowStatus()
            if cflow_start and cflow_end:
                cflow_rates = self.controller.calculateCFlowRate(cflow_start, cflow_end, interval)

        t = time.time()

        out = open(self.config.statslog, "a")

        for (node, error, vals) in top:
            if not error:
                for proc in vals:
                    type = proc["proc"]
                    for (val, key) in proc.items():
                        if val != "proc":
                            out.write("%s %s %s %s %s\n" % (t, node, type, val, key))
            else:
                out.write("%s %s error error %s\n" % (t, node, error))

        for (node, netif, error, vals) in capstats:
            if not error:
                for (key, val) in vals.items():
                    out.write("%s %s interface %s %s\n" % (t, node, key, val))

                    if key == "pkts" and str(node) != "$total":
                        # Report if we don't see packets on an interface.
                        tag = "lastpkts-%s" % node.name.lower()

                        if tag in self.config.state:
                            last = float(self.config.state[tag])
                        else:
                            last = -1.0

                        if float(val) == 0.0 and last != 0.0:
                            self.ui.info("%s is not seeing any packets on interface %s" % (node.host, netif))

                        if float(val) != 0.0 and last == 0.0:
                            self.ui.info("%s is seeing packets again on interface %s" % (node.host, netif))

                        self.config._setState(tag, val)

            else:
                out.write("%s %s error error %s\n" % (t, node, error))

        for (port, error, vals) in cflow_rates:
            if not error:
                for (key, val) in vals.items():
                    out.write("%s cflow %s %s %s\n" % (t, port.lower(), key, val))

        out.close()

    def checkDiskSpace(self):
        minspace = float(self.config.mindiskspace)
        if minspace == 0.0:
            return

        results = self.controller.df(self.config.hosts())
        for (nodehost, dfs) in results:
            host = nodehost.split("/")[1]

            for df in dfs:
                if df[0] == "FAIL":
                    # A failure here is normally caused by a host that is down, so
                    # we don't need to output the error message.
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

                self.config._setState(key, "%.1f" % perc)

    def expireLogs(self):
        i = int(self.config.logexpireinterval)
        i2 = int(self.config.statslogexpireinterval)

        if i == 0 and i2 == 0:
            return

        (success, output) = execute.runLocalCmd(os.path.join(self.config.scriptsdir, "expire-logs"))

        if not success:
            self.ui.error("expire-logs failed\n\n")
            self.ui.error(output)

    def checkHosts(self):
        for node in self.config.hosts(nolocal=True):
            tag = "alive-%s" % node.host.lower()
            # TODO: fix
            #alive = execute.isAlive(node.addr) and "1" or "0"
            alive = "1"

            if tag in self.config.state:
                previous = self.config.state[tag]

                if alive != previous:
                    # TODO: fix
                    #plugin.Registry.hostStatusChanged(node.host, alive == "1")
                    self.ui.info("host %s %s" % (node.host, alive == "1" and "up" or "down"))

            self.config._setState(tag, alive)


    def updateHTTPStats(self):
        # Create meta file.
        if not os.path.exists(self.config.statsdir):
            try:
                os.makedirs(self.config.statsdir)
            except OSError as err:
                self.ui.error("failure creating directory: %s" % err)
                return

            self.ui.info("creating directory for stats file: %s" % self.config.statsdir)

        metadat = os.path.join(self.config.statsdir, "meta.dat")
        try:
            meta = open(metadat, "w")
        except IOError as err:
            self.ui.error("failure creating file: %s" % err)
            return

        for node in self.config.hosts():
            meta.write("node %s %s %s\n" % (node, node.type, node.host))

        meta.write("time %s\n" % time.asctime())
        meta.write("version %s\n" % self.config.version)

        try:
            meta.write("os %s\n" % execute.runLocalCmd("uname -a")[1][0])
        except IndexError:
            meta.write("os <error>\n")

        try:
            meta.write("host %s\n" % execute.runLocalCmd("hostname")[1][0])
        except IndexError:
            meta.write("host <error>\n")

        meta.close()

        wwwdir = os.path.join(self.config.statsdir, "www")
        if not os.path.isdir(wwwdir):
            try:
                os.makedirs(wwwdir)
            except OSError as err:
                self.ui.error("failed to create directory: %s" % err)
                return

        # Append the current stats.log in spool to the one in ${statsdir}
        dst = os.path.join(self.config.statsdir, os.path.basename(self.config.statslog))
        try:
            fdst = open(dst, "a")
        except IOError as err:
            self.ui.error("failed to append to file: %s" % err)
            return

        fsrc = open(self.config.statslog, "r")
        shutil.copyfileobj(fsrc, fdst)
        fdst.close()
        fsrc.close()

        # Update the WWW data
        statstocsv = os.path.join(self.config.scriptsdir, "stats-to-csv")

        (success, output) = execute.runLocalCmd("%s %s %s %s" % (statstocsv, self.config.statslog, metadat, wwwdir))
        if not success:
            self.ui.error("stats-to-csv failed")
            return

        os.unlink(self.config.statslog)
        shutil.copy(metadat, wwwdir)


    def runCronCmd(self):
        # Run external command if we have one.
        if self.config.croncmd:
            (success, output) = execute.runLocalCmd(self.config.croncmd)
            if not success:
                self.ui.error("failure running croncmd: %s" % self.config.croncmd)

