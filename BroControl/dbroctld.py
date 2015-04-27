#! /usr/bin/python

import SocketServer
import socket
import time
import traceback

from collections import defaultdict
from Queue import Queue
from threading import Thread

from BroControl.broctl import BroCtl

# Global options
peer_timeout = 5
handler_sleep_time = 0.2
server_port = 10042

class DBroCtld(Thread):
    def __init__(self, logs, basedir):
        Thread.__init__(self)

        self.logs = logs
        self.running = True
        self.squeue = Queue()
        self.outbound = []
        self.basedir = basedir

    def init_server(self):
        # BroCtl
        self.broctl = BroCtl(self.basedir, ui=TermUI())
        self.parent_address = self.broctl.config.getHead().host
        self.server_address = self.broctl.config.getLocalNode().host
        print "server_host is", self.server_address, "parent is", self.parent_address

        # Server
        print "starting bserver... "
        self.bserver = BSocketServer(self.squeue, (self.server_address, server_port), BSocketHandler, bind_and_activate=True)
        self.server_thread = Thread(target=self.bserver.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

        # Client only if we are not the root node of the hierarchy
        if self.parent_address and self.parent_address != self.server_address:
            print "starting bclient... "
            self.bclient = BClient((self.parent_address, server_port), self.squeue)
            self.bclient.start()

        print "done initializing"

    def run(self):
        self.init_server()

        while self.running:
            self.recv()

    def recv(self):
        (dtype, data) = self.squeue.get()
        print "dtype:", dtype, "data:", data

        if dtype not in ["command", "peer-connect", "peer-disconnect"]:
            raise RuntimeError("DBroctlD: malformed data type", dtype, "received")

        if dtype == "command":
            self.handleCommand(data)

        elif dtype == "peer-connect":
            self.handlePeerConnect(data)

        elif dtype == "peer-disconnect":
            self.handlePeerDisconnect(data)

    def handleCommand(self, data):
        args= data.split(" ")
        cmd = args[0]
        args.remove(cmd)
        print "received command", cmd

        # 1. Execute command
        func = getattr(self.broctl, cmd, self.noop)
        if not hasattr(func, 'api_exposed'):
            print "unknown command, ignoring it"
            return

        try :
            res = func(*args)
        except Exception as e:
            res = traceback.format_exc()

        # 2. Forward command
        self.forwardCommand(cmd)

    def handlePeerConnect(self, peer):
        self.outbound.append(peer)
        print "peer", peer, "connected, size outbound", len(self.outbound)

    def handlePeerDisconnect(self, peer):
        print "peer", peer, "disconnected"
        self.outbound.remove(peer)

    def forwardCommand(self, cmd):
        for peer in self.outbound:
            self.bserver.send(peer, cmd)

    def noop(self, *args, **kwargs):
        return True

####################################

class BSocketServer(SocketServer.ThreadingMixIn, SocketServer.ThreadingTCPServer):

    def __init__(self, squeue, server_address, RequestHandlerClass, bind_and_activate=True):
        self.squeue = squeue
        self.outbound = {}
        SocketServer.ThreadingTCPServer.__init__(self, server_address, RequestHandlerClass, bind_and_activate)

    def server_activate(self):
        print "server activated..."
        self.socket.listen(self.request_queue_size)

    def peer_connected(self, peer, handler):
        self.outbound[peer] = handler
        self.squeue.put(("peer-connect", peer))

    def peer_disconnected(self, peer):
        self.outbound.pop(peer)
        self.squeue.put(("peer-disconnect", peer))

    def receive_data(self, data):
        self.squeue.put(("command", data))

    def send(self, peer, data):
        print "forward cmd", data, "to", peer
        self.outbound[peer].send(data)

####################################

class BSocketHandler(SocketServer.BaseRequestHandler):

    def setup(self):
        self.server.peer_connected(self.client_address, self)

    def handle(self):
        counter = 0

        while True:
            data = self.request.recv(1024).strip()

            # When there is data, hand over to server
            if data != "":
                self.server.receive_data(data)
                self.request.sendto("Ack", self.client_address)
                counter = 0
            else:
                counter += 1
                # timeout occurred, disconnect from client
                if counter >= (peer_timeout / handler_sleep_time):
                    break
                time.sleep(handler_sleep_time)

    def send(self, data):
        self.request.sendto(data, self.client_address)

    def finish(self):
        self.server.peer_disconnected(self.client_address)

####################################

class BClient(Thread):
    def __init__(self, server_address, queue):
        Thread.__init__(self)

        self.server_address = server_address
        self.cqueue = queue
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect(server_address)

    def run(self):
        try:
            counter = 0
            while True:
                data = self.socket.recv(1024)
                if data:
                    print "received data", data
                    self.cqueue.put(("command", data))
                    counter = 0
                else:
                    counter +=1

                if counter >= (peer_timeout / handler_sleep_time):
                    break

            time.sleep(handler_sleep_time)

        finally:
            self.finish()

    def finish(self):
        self.socket.close()

####################################

class TermUI:
    def __init__(self):
        pass

    def output(self, msg):
        print(msg)
    warn = info = output

    def error(self, msg):
        print("ERROR", msg)

####################################

class Logs:
    def __init__(self):
        self.store = defaultdict(list)

    def append(self, id, stream, txt):
        self.store[id].append((stream, txt))

    def get(self, id, since=0):
        msgs = self.store.get(id) or []
        return msgs[since:]

####################################

def main(basedir='/bro'):
    logs = Logs()

    d = DBroCtld(logs, basedir)
    d.start()

if __name__ == "__main__":
    main()
