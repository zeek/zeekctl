import collections
import json
import subprocess
import select
import textwrap
import time
import os
from threading import Thread

from BroControl import py3bro
Queue = py3bro.Queue
Empty = py3bro.Empty


def get_muxer(shell):
    muxer = r"""
    import json
    import os
    import sys
    import subprocess
    import signal
    import select

    TIMEOUT=120

    def w(s):
        sys.stdout.write(json.dumps(s) + "\n")
        sys.stdout.flush()

    def exec_commands(cmds):
        procs = []
        for i, cmd in enumerate(cmds):
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=__SHELL__)
                procs.append((i, proc))
            except Exception as e:
                w( (i, (1, '', str(e))) )
        return procs

    w("ready")
    commands = []
    signal.alarm(TIMEOUT)
    for line in iter(sys.stdin.readline, "done\n"):
        commands.append(json.loads(line))
    procs = exec_commands(commands)

    cmd_mapping = {}
    fd_mapping = {}
    allfds = set()
    for i, proc in procs:
        o = {"idx": i, "proc": proc, "stdout": [], "stderr": [], "waiting": 2}
        fd_mapping[proc.stdout] = o["stdout"]
        fd_mapping[proc.stderr] = o["stderr"]
        cmd_mapping[proc.stdout] = o
        cmd_mapping[proc.stderr] = o
        allfds.update([proc.stderr, proc.stdout])

    while allfds:
        r, _, _ = select.select(allfds, [], [])
        for fd in r:
            output = os.read(fd.fileno(), 1024)
            if output:
                fd_mapping[fd].append(output)
                continue

            cmd = cmd_mapping[fd]
            cmd["waiting"] -= 1
            if cmd["waiting"] != 0:
                continue

            proc = cmd["proc"]
            res = proc.wait()
            out = "".join(cmd["stdout"])
            err = "".join(cmd["stderr"])
            w( (cmd["idx"], (res, out, err)) )
            allfds.remove(proc.stdout)
            allfds.remove(proc.stderr)

    w("done")
    """

    muxer = textwrap.dedent(muxer.replace("__SHELL__", str(shell)))

    return muxer.encode("zlib").encode("base64").replace("\n", "")


CmdResult = collections.namedtuple("CmdResult", "status stdout stderr")

class SSHMaster:
    def __init__(self, host, localaddrs):
        self.host = host
        self.base_cmd = [
            "ssh",
            host,
        ]
        self.need_connect = True
        self.master = None
        self.localaddrs = localaddrs

    def islocal(self, addr):
        return addr == "localhost" or addr in self.localaddrs

    def connect(self):
        if self.need_connect:
            if self.islocal(self.host):
                cmd = ["sh"]
            else:
                cmd = self.base_cmd + ["sh"]
            self.master = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.PIPE, close_fds=True, preexec_fn=os.setsid)
            self.need_connect = False

    def readline_with_timeout(self, timeout):
        readable, _, _ = select.select([self.master.stdout], [], [], timeout)
        if not readable:
            return False
        return self.master.stdout.readline()

    def exec_command(self, cmd, shell=False, timeout=60):
        return self.exec_commands([cmd], shell, timeout)[0]

    def exec_commands(self, cmds, shell=False, timeout=60):
        self.send_commands(cmds, shell, timeout)
        return self.collect_results(timeout)

    def send_commands(self, cmds, shell=False, timeout=10):
        self.connect()
        run_mux = """python -c 'exec("%s".decode("base64").decode("zlib"))'\n""" % get_muxer(shell)
        self.master.stdin.write(run_mux)
        self.master.stdin.flush()
        self.readline_with_timeout(timeout)
        for cmd in cmds:
            self.master.stdin.write(json.dumps(cmd) + "\n")
        self.master.stdin.write("done\n")
        self.master.stdin.flush()
        self.sent_commands = len(cmds)

    def collect_results(self, timeout=60):
        outputs = [Exception("SSH Timeout")] * self.sent_commands
        while True:
            line = self.readline_with_timeout(timeout)
            if not line:
                self.close()
                break
            resp = json.loads(line)
            if resp == "done":
                break
            idx, out = resp
            outputs[idx] = CmdResult(*out)
        return outputs

    def ping(self, timeout=5):
        output = self.exec_command(["/bin/echo", "ping"])
        return output and output.stdout.strip() == "ping"

    def close(self):
        if not self.master:
            return
        self.master.stdin.close()
        try:
            self.master.kill()
        except OSError:
            pass
        self.master.wait()
        self.master = None
        self.need_connect = True
    __del__ = close


STOP_RUNNING = object()

class HostHandler(Thread):
    def __init__(self, host, ui, localaddrs):
        self.ui = ui
        self.host = host
        self.q = Queue()
        self.alive = "Unknown"
        self.master = None
        Thread.__init__(self)
        self.daemon = True
        self.localaddrs = localaddrs

    def shutdown(self):
        self.q.put((STOP_RUNNING, None, None))

    def connect(self):
        if self.master:
            self.master.close()
        self.master = SSHMaster(self.host, self.localaddrs)

    def ping(self):
        try:
            return self.master.ping()
        except Exception as e:
            self.ui.output("Error in ping for %s" % self.host)
            return False

    def connect_and_ping(self):
        if self.alive is not True:
            self.connect()
        self.alive = self.ping()

    def run(self):
        while True:
            if self.iteration():
                return

    def iteration(self):
        try:
            item, shell, rq = self.q.get(timeout=30)
        except Empty:
            self.connect_and_ping()
            return False

        if item is STOP_RUNNING:
            return True

        self.connect_and_ping()
        if not self.alive:
            resp = [Exception("Host %s is not alive" % self.host)] * len(item)
            rq.put(resp)
            return False

        try:
            resp = self.master.exec_commands(item, shell)
        except Exception as e:
            self.ui.output("Exception in iteration for %s" % self.host)
            self.alive = False
            time.sleep(2)
            resp = [e] * len(item)
        rq.put(resp)

        return False

    def send_commands(self, commands, shell, rq):
        self.q.put((commands, shell, rq))
            

class MultiMasterManager:
    def __init__(self, ui, localaddrs=[]):
        self.ui = ui
        self.masters = {}
        self.response_queues = {}
        self.localaddrs = localaddrs

    def setup(self, host):
        if host not in self.masters:
            self.masters[host] = HostHandler(host, self.ui, self.localaddrs)
            self.masters[host].start()

    def send_commands(self, host, commands, shell=False):
        self.setup(host)
        rq = Queue()
        self.response_queues[host] = rq
        self.masters[host].send_commands(commands, shell, rq)

    def get_result(self, host, timeout):
        rq = self.response_queues[host]
        try:
            return rq.get(timeout=timeout)
        except Empty:
            self.shutdown(host)
            return [Exception("Timeout")] #FIXME: needs to be the right length

    def exec_command(self, host, command, timeout=30):
        return self.exec_commands(host, [command], timeout)[0]

    def exec_commands(self, host, commands, timeout=65):
        self.setup(host)
        self.send_commands(host, commands)
        return self.get_result(host, timeout)

    def exec_multihost_commands(self, cmds, shell=False, timeout=65):
        hosts = collections.defaultdict(list)
        for host, cmd in cmds:
            hosts[host].append(cmd)

        for host, cmds in hosts.items():
            self.send_commands(host, cmds, shell)

        for host in hosts:
            for res in self.get_result(host, timeout):
                yield host, res

    def host_status(self):
        for h, o in self.masters.items():
            yield h, o.alive

    def shutdown(self, host):
        self.masters[host].shutdown()
        del self.masters[host]

    def shutdown_all(self):
        for handler in self.masters.values():
            handler.shutdown()
        self.masters = {}

    __del__ = shutdown_all

