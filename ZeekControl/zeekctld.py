from __future__ import print_function
from collections import defaultdict
from threading import Thread, Lock
from Queue import Queue
import os
import time
import random
import traceback

from ZeekControl import config
from ZeekControl import version
from ZeekControl.zeekctl import ZeekCtl
from ZeekControl import ser as json

from ZeekControl import web

STOP_RUNNING = object()

class TermUI:
    def __init__(self):
        pass

    def info(self, msg):
        print(msg)
    warn = info

    def error(self, msg):
        print("ERROR", msg)

class Logs:
    def __init__(self):
        self.store = defaultdict(list)

    def append(self, id, stream, txt):
        self.store[id].append((stream, txt))

    def get(self, id, since=0):
        msgs = self.store.get(id) or []
        return msgs[since:]

class Common:
    def dump(self, *args):
        return json.dumps(*args)
    def load(self, msg):
        return json.loads(msg)

class ZeekCtrldWorker(Thread, Common):
    def __init__(self, command_queue):
        self.q = Queue()
        Thread.__init__(self)
        self.daemon = True
        self.command_queue = command_queue
        self._id = None

    def send(self, id, cmd, *args):
        self.q.put((id, cmd, args))

    def run(self):
        #FIXME: deepcopy breaks here if i set ui=self
        self.zeekctl = ZeekCtl(ui=TermUI())
        self.zeekctl.ui = self
        self.zeekctl.controller.ui = self
        self.zeekctl.executor.ui = self
        while True:
            if self.iteration():
                return

    def noop(self, *args, **kwargs):
        return True

    def iteration(self):
        id, cmd, args = self.q.get()
        self._id = id

        if cmd is STOP_RUNNING:
            return True

        func = getattr(self.zeekctl, cmd, self.noop)

        def respond(r):
            self.call("result", id, r)

        if not hasattr(func, 'api_exposed'):
            return respond("invalid function")

        try :
            res = func(*args)
        except Exception as e:
            res = traceback.format_exc()
        respond(res)

    def call(self, func, *args):
        self.command_queue.put((None, func, args))

    def info(self, msg):
        return self.call("info", self._id, msg)

    def error(self, msg):
        return self.call("err", self._id, msg)
    warn = error

class ZeekCtld(Thread, Common):
    def __init__(self, command_queue, logs):
        Thread.__init__(self)
        self.daemon = True
        self.logs = logs
        self.command_queue = command_queue
        self.worker = ZeekCtrldWorker(self.command_queue)

        self.results = {}
        self.running = True

        self.id_gen = iter(range(10000000)).next

        self.init()

    def init(self):
        self.worker.start()

    def recv(self):
        msg = self.command_queue.get()
        print("Received", msg)
        return msg

    def run(self):
        return self._run()

    def handle_result(self, id, result):
        print("Got result id=%r result=%r" % (id, result))
        self.results[id] = result
        return "ok"

    def handle_out(self, id, txt):
        print("Got %s id=%r result=%r" % ('out', id, txt))
        self.logs.append(id, 'out', txt)
        return "ok"

    def handle_info(self, id, txt):
        print("Got %s id=%r result=%r" % ('info', id, txt))
        self.logs.append(id, 'info', txt)
        return "ok"

    def handle_err(self, id, txt):
        print("Got %s id=%r result=%r" % ('err', id, txt))
        self.logs.append(id, 'err', txt)
        return "ok"

    def handle_getresult(self, id):
        result = self.results.get(id)
        if result:
            del self.results[id]
        print("sending result=%r for id=%r" % (result, id))
        return result

    def handle_getlog(self, id, since):
        result = self.logs.get(id, since)
        print("sending log=%r for id=%r" % (result, id))
        return result

    def _run(self):
        while self.running:
            (rq, cmd, args) = self.recv()
            func = getattr(self, 'handle_' + cmd, None)
            if func:
                res = func(*args)
                if rq:
                    rq.put(res)
            else:
                t_id = self.send_to_worker(cmd, *args)
                rq.put(t_id)

    def send_to_worker(self, cmd, *args):
        t_id = self.id_gen()
        self.worker.send(t_id, cmd, *args)
        print("started id=%r cmd=%r args=%r" % (t_id, cmd, args))
        return t_id

class Client(Common):
    def __init__(self, command_queue):
        self.command_queue = command_queue

    def call(self, func, *args):
        rq = Queue()
        self.command_queue.put((rq, func, args))
        return rq.get()

    def sync_call(self, func, *args):
        id = self.call(func, *args)
        print("got id", id)
        while True:
            res = self.getresult(id)
            if res:
                return res
            time.sleep(0.1)

    def result(self, id, result):
        return self.call("result", id, result)

    def getresult(self, id):
        return self.call("getresult", id)

    def getlog(self, id, since=0):
        return self.call("getlog", id, since)

def main(basedir='/zeek'):
    logs = Logs()

    command_queue = Queue()
    d = ZeekCtld(command_queue, logs)

    d.start()

    c = Client(command_queue)

    ww = Thread(target=web.run_app, args=[c])
    ww.start()
    print("I Got:", c.sync_call('status'))
    for x in range(20):
        time.sleep(1)

if __name__ == "__main__":
    main()
