#! /usr/bin/python

import SocketServer
import socket
import time
import traceback
import logging

from collections import defaultdict
from Queue import Queue
from threading import Thread

from BroControl.broctl import BroCtl

# Global options
# TODO need to be moved to options.py
server_port = 10042
peer_timeout = 5
polling_interval = 0.2

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
        self.parent_address = self.broctl.config.getHead().addr
        self.server_address = self.broctl.config.getLocalNode().addr
        print "server_host is", self.server_address, "parent is", self.parent_address

        # Server
        print "starting bserver... "
        self.bserver = BSocketServer(self.squeue, (self.server_address, server_port), BSocketHandler, bind_and_activate=True)
        self.server_thread = Thread(target=self.bserver.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.daemon_threads = True
        self.server_thread.start()
        logging.debug("DBroctlD SocketServer started")

        self.bclient  = None
        # Client only if we are not the root node of the hierarchy
        if self.parent_address and self.parent_address != self.server_address:
            print "starting bclient... "
            print "connecting to parent", self.parent_address, "on port", server_port
            self.bclient = BClient((self.parent_address, server_port), self.squeue)
            self.client_thread = Thread(target=self.bclient.run)
            self.client_thread.daemon = True
            self.client_thread.start()
            logging.debug("DClient started")

    def stop(self):
        print "exit dbroctld..."

        # Shutting down the client
        if self.bclient:
            self.bclient.run = False
            self.bclient.stop()

        # Shutting down the server
        self.bserver.stop()
        self.bserver.shutdown()

        # Shutting down ourselves
        self.running = False

        # Kill the local thread
        logging.debug("DBroctld stopped")

    def run(self):
        self.init_server()
        while self.running:
            self.recv()

    def recv(self):
        (dtype, data) = self.squeue.get()
        logging.debug("dtype: " + str(dtype) + " data: " + str(data))

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
        logging.debug("received command " + str(cmd))

        if "shutdown" in cmd:
            self.forwardCommand(cmd)
            self.stop()
            return

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
        logging.debug("peer " + str(peer) + " connected, " + str(len(self.outbound)) + " outbound connections")
        print ("peer " + str(peer) + " connected, " + str(len(self.outbound)) + " outbound connections")

    def handlePeerDisconnect(self, peer):
        print "peer", peer, "disconnected"
        if peer in self.outbound:
            logging.debug(" outbound peer " + str(peer) + " disconnected")
            self.outbound.remove(peer)

    def forwardCommand(self, cmd):
        if self.outbound:
            logging.debug("forward cmd to ")

        for peer in self.outbound:
            logging.debug(" - " + str(peer))
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
        logging.debug("server activated")
        self.socket.listen(self.request_queue_size)

    def peer_connected(self, peer, handler):
        logging.debug("SocketServer::Peer connected: " + str(peer))

        self.outbound[peer] = handler
        self.squeue.put(("peer-connect", peer))

    def peer_disconnected(self, peer):
        logging.debug("SocketServer:: disconnect peer " + str(peer))
        self.outbound.pop(peer)
        self.squeue.put(("peer-disconnect", peer))

    def receive_data(self, data):
        self.squeue.put(("command", data))

    def send(self, peer, data):
        if peer in self.outbound:
            self.outbound[peer].send(data)

    def stop(self):
        self.socket.close()
        logging.debug("SocketServer stopped")

####################################

class BSocketHandler(SocketServer.BaseRequestHandler):

    def setup(self):
        logging.debug("SocketHandler for client " + str(self.client_address) + " created")
        self.running = True
        self.server.peer_connected(self.client_address, self)

    def handle(self):
        try:
            counter = 0
            while self.running:
                data = self.request.recv(1024).strip()

                if data != "":
                    counter = 0
                    logging.debug("Handler for peer " + str(self.client_address) + " received data: " + str(data))
                    self.server.receive_data(data)
                    self.request.sendto("Ack", self.client_address)
                    if "shutdown" in data:
                        self.stop()
                else:
                    counter += 1

                if counter >= (peer_timeout / polling_interval):
                    break

                # Go to sleep
                time.sleep(polling_interval)

        finally:
            self.stop()

    def send(self, data):
        self.request.sendto(data, self.client_address)

    def finish(self):
        logging.debug("handler for" + str(self.client_address) + " terminates")
        self.server.peer_disconnected(self.client_address)

    def stop(self):
        self.running = False

####################################

class BClient():
    def __init__(self, server_address, queue):
        #Thread.__init__(self)

        self.server_address = server_address
        self.cqueue = queue
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect(server_address)
        self.running = True

    def run(self):
        try:
            counter = 0
            while self.running:
                data = self.socket.recv(1024)
                if data:
                    print "received data", data
                    self.cqueue.put(("command", data))
                    counter = 0
                else:
                    counter +=1

                if counter >= (peer_timeout / polling_interval):
                    break

            # Go to sleep
            time.sleep(polling_interval)

        finally:
            self.finish()

    def finish(self):
        self.socket.close()

    def stop(self):
        self.running = False
        self.finish()

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
