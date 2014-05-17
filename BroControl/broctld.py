from collections import defaultdict
from threading import Thread, Lock
from Queue import Queue
from nanomsg import Socket, REQ, REP
import time
import random

from BroControl.broctl import BroCtl
from BroControl import ser as json

class State:
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[key] = value
    setstate = set

    def get(self, key):
        return self.store.get(key)
    getstate = get

class TermUI:
    def __init__(self):
        pass

    def out(self, msg):
        print msg

    def err(self, msg):
        print "ERROR", msg

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

class Daemon(Common):
    change_funcs = set()
    bg_tasks = []
    def __init__(self, state, logs, worker_class):
        self.state = state
        self.logs = logs
        self.worker_class = worker_class

        self.sock = Socket(REP)
        self.sock.bind('inproc://server')
        self.sock.bind('ipc:///bro/socket')

        self.results = {}
        self.threads = {}
        self.running = True

        self.change_lock = Lock()

        self.id_gen = iter(range(10000000)).next

        self.init()

    def init(self):
        pass

    def recv(self):
        msg = self.sock.recv()
        #print "Received", self.load(msg)
        return self.load(msg)

    def send(self, *args):
        msg = self.dump(*args)
        return self.sock.send(msg)

    def run(self):
        t = Thread(target=self._bg)
        t.start()
        t = Thread(target=self._run)
        t.start()
        return t

    def _bg(self):
        sock = Socket(REQ)
        sock.connect('inproc://server')
        while self.running:
            for func in self.bg_tasks:
                msg = self.dump((func, []))
                sock.send(msg)
                self.load(sock.recv())
            time.sleep(10)

    def handle_result(self, id, result):
        print "Got result id=%r result=%r" % (id, result)
        self.results[id] = result
        self.send("ok")

    def handle_setstate(self, key, value):
        print "Set state key=%r value=%r" % (key, value)
        self.state.set(key, value)
        self.send("ok")

    def handle_getstate(self, key):
        value = self.state.get(key)
        print "Get state key=%r value=%r" % (key, value)
        self.send(value)

    def handle_out(self, id, txt):
        print "Got %s id=%r result=%r" % ('out', id, txt)
        self.logs.append(id, 'out', txt)
        self.send("ok")

    def handle_err(self, id, txt):
        print "Got %s id=%r result=%r" % ('err', id, txt)
        self.logs.append(id, 'err', txt)
        self.send("ok")

    def handle_getresult(self, id):
        result = self.results.get(id)
        if result:
            del self.results[id]
            del self.threads[id]
        print "sending result=%r for id=%r" % (result, id)
        self.send(result)

    def handle_getlog(self, id, since):
        result = self.logs.get(id, since)
        print "sending log=%r for id=%r" % (result, id)
        self.send(result)

    def _run(self):
        while self.running:
            (cmd, args) = self.recv()
            func = getattr(self, 'handle_' + cmd, None)
            if func:
                func(*args)
                continue

            t_id, t = self.spawn_worker(cmd, args)
            self.send(t_id)
            self.threads[t_id] = t
            print "started thread for id=%r func=%r args=%r" % (t_id, func, args)

    def spawn_worker(self, cmd, args):
        t_id = self.id_gen()
        target = lambda: self.wrap(t_id, cmd, args)
        t = Thread(target=target)
        t.start()
        return t_id, t

    def noop(self, *args, **kwargs):
        return True

    def wrap(self, id, cmd, args):
        w = self.worker_class(id)
        func = getattr(w, cmd, self.noop)

        def respond(r):
            w.cl.call("result", id, r)
            w.cl.close()

        if not hasattr(func, 'api_exposed'):
            return respond("invalid function")

        if hasattr(func, 'lock_required'):
            self.change_lock.acquire()
        try :
            try :
                res = func(*args)
            except Exception, e:
                res = repr(e)
            respond(res)
        finally:
            if hasattr(func, 'lock_required'):
                self.change_lock.release()

class Client(Common):
    def __init__(self, uri='inproc://server', id=None):
        self.sock = Socket(REQ)
        self.sock.connect(uri)
        self.id=id

    def close(self):
        self.sock.close()

    def call(self, func, *args):
        msg = self.dump((func, args))
        self.sock.send(msg)
        return self.load(self.sock.recv())

    def sync_call(self, func, *args):
        id = self.call(func, *args)
        print "got id", id
        while True:
            res = self.getresult(id)
            if res:
                return res
            time.sleep(0.1)

    def result(self, id, result):
        return self.call("result", id, result)

    def getresult(self, id):
        return self.call("getresult", id)

    def getstate(self, key):
        return self.call("getstate", key)

    def setstate(self, key, value):
        return self.call("setstate", key, value)

    def getlog(self, id, since=0):
        return self.call("getlog", id, since)

    def info(self, msg):
        return self.call("out", self.id, msg)

    def error(self, msg):
        return self.call("err", self.id, msg)
    warn = error

class Broctld(Daemon):
    pass
    #bg_tasks =['refresh', 'cron']
    #change_funcs = 'start stop exec cron'.split()

NODES = ['node-%d' %x for x in range(48)]

def broctl_worker_factory(id):
    cl = Client(id=id)
    worker = BroCtl(ui=cl)
    worker.cl = cl
    return worker

def main():

    state = State()
    logs = Logs()

    d = Broctld(state, logs, broctl_worker_factory)
    dt = d.run()
    dt.join()

if __name__ == "__main__":
    main()
