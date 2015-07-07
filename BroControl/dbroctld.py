#! /usr/bin/python

import SocketServer
import socket
import time
import traceback
import logging
import json

from collections import defaultdict
from Queue import Queue
from threading import Thread
from BroControl.broctl import BroCtl
import pybroker


# Global options
# TODO need to be moved to options.py
server_port = 9999
peer_timeout = 50
polling_interval = 0.2

BROKER_COM = True

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
        self.parent_address = self.broctl.config.get_head().addr
        self.server_address = self.broctl.config.get_local().addr

        # Server
        print "starting dbroctld... "
        print "  -- dbroctld listens on", self.server_address, "::", server_port
        self.bserver = BSocketServer(self.squeue, (self.server_address, server_port), BSocketHandler, bind_and_activate=True)
        self.server_thread = Thread(target=self.bserver.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.daemon_threads = True
        self.server_thread.start()
        logging.debug("DBroctlD SocketServer started")

        self.bclient = None
        # Client only if we are not the root node of the hierarchy
        if self.parent_address and self.parent_address != self.server_address:
            print "  -- parent is", self.parent_address
            self.bclient = BClient((self.parent_address, server_port), self.squeue)
            self.client_thread = Thread(target=self.bclient.run)
            self.client_thread.daemon = True
            self.client_thread.start()
            logging.debug("DClient started")
        else:
            print "  -- we are the root node of the deep cluster"

    def init_overlay(self):
        # Install the local node, its cluster nodes, and its peers
        self.broctl.install()
        # Start the peers in the deep cluster recursively
        self.broctl.create_overlay()

    def run(self):
        self.init_server()
        self.init_overlay()
        while self.running:
            self.recv()

    def recv(self):
        (dtype, data) = self.squeue.get()
        logging.debug("dtype: " + str(dtype) + " with data: " + str(data))

        if dtype not in ["msg", "peer-connect", "peer-disconnect"]:
            logging.debug("DBroctlD: malformed data type", dtype, "received")
            raise RuntimeError("DBroctlD: malformed data type", dtype, "received")

        if dtype == "msg":
            self.handleMessage(data)

        elif dtype == "peer-connect":
            self.handlePeerConnect(data)

        elif dtype == "peer-disconnect":
            self.handlePeerDisconnect(data)

    def handleMessage(self, msg):
        logging.debug("handleMessage: msg received: " +  str(msg))

        if 'type' not in msg.keys():
            logging.debug("Error: received a msg with no type")
            raise RuntimeError("malformed message received")

        if msg["type"] == "command":
            self.handleCommand(msg)

        elif msg["type"] == "ack":
            logging.debug("Acknowledgement received")

        elif msg["type"] == "result":
            self.handleResult(msg)

        else:
            logging.debug("handleMessage: unknown message type received")
            raise RuntimeError("message type unknown")

    def handleCommand(self, msg):
        cmd = msg['payload']

        # Distinguish between command and its parameters
        args= cmd.split(" ")
        cmd = args[0]
        args.remove(cmd)

        logging.debug("executing cmd " + str(cmd) + " with args " + str(args))
        # Execute command...
        func = getattr(self.broctl, cmd, self.noop)
        logging.debug("func " + str(func))

        if hasattr(func,  'api_exposed'):
            res = None

            try:
                res = func(*args)
            except Exception:
                res = traceback.format_exc()

            if res:
                logging.debug("result of cmd " + str(cmd) + " is " + str(res.get_node_output()))

            # Forward command ...
            self.forwardCommand(cmd)

        elif cmd == 'shutdown':
            # Forward command ...
            self.forwardCommand(cmd)
            # Stop all local bro processes
            self.stop()

        else:
            logging.debug("handleCommand: unknown command, ignoring it")

    def handleResult(self, res):
        logging.debug("result received: " + str(res))

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
            logging.debug("forward cmd \"" + str(cmd) + "\" to ")

        for peer in self.outbound:
            logging.debug(" - " + str(peer))
            self.sendCommand(peer, cmd)

    def sendCommand(self, peer, cmd):
        msg = {'type':'command', 'payload':cmd}
        self.bserver.send(peer, msg)

    def noop(self, *args, **kwargs):
        return True

    def stop(self):
        print "exit dbroctld..."
        logging.debug("exit dbroctld")

        # Shutting down the local bro instances
        self.broctl.stop()

        # Shutting down the client
        if self.bclient:
            self.bclient.run = False
            self.bclient.stop()

        # Shutting down the server
        self.bserver.stop()
        self.bserver.shutdown()

        # Shutting down ourselves
        self.running = False

        logging.debug("DBroctld stopped")


class BSocketServer(SocketServer.ThreadingMixIn, SocketServer.ThreadingTCPServer):

    def __init__(self, squeue, server_address, RequestHandlerClass, bind_and_activate=True):
        self.squeue = squeue
        self.outbound = {}
        SocketServer.ThreadingTCPServer.__init__(self, server_address, RequestHandlerClass, bind_and_activate)

    def server_activate(self):
        self.socket.listen(self.request_queue_size)

    def peer_connected(self, peer, handler):
        logging.debug("Peer connected: " + str(peer))

        self.outbound[peer] = handler
        self.squeue.put(("peer-connect", peer))

    def peer_disconnected(self, peer):
        logging.debug("Peer disconnected: " + str(peer))
        self.outbound.pop(peer)
        self.squeue.put(("peer-disconnect", peer))

    def receive_data(self, data):
        self.squeue.put(("msg", data))

    def send(self, peer, data):
        if peer in self.outbound:
            self.outbound[peer].send(data)

    def stop(self):
        self.socket.close()
        logging.debug("SocketServer stopped")


class BSocketHandler(SocketServer.BaseRequestHandler):
    def setup(self):
        logging.debug("SocketHandler for peer " + str(self.client_address) + " created")
        self.running = True
        self.server.peer_connected(self.client_address, self)

    def handle(self):
        try:
            counter = 0
            while self.running:
                data = self.request.recv(1024).strip()
                if data != "":
                    data = json.loads(data)
                    counter = 0
                    logging.debug("Handler for peer " + str(self.client_address) + " received data: " + str(data))
                    self.server.receive_data(data)

                    # Send a reply
                    if 'type' in data.keys() and data['type'] != 'ack':
                        reply = {'type': 'ack', 'payload':'ack'}
                        self.request.sendto(json.dumps(reply), self.client_address)

                    # Stop the handler if we receive a shutdown command
                    if 'type' in data.keys() and data['type'] == 'command' and data['payload'] == 'shutdown':
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
        self.request.sendto(json.dumps(data), self.client_address)

    def finish(self):
        logging.debug("Handler for peer " + str(self.client_address) + " terminates")
        self.server.peer_disconnected(self.client_address)

    def stop(self):
        self.running = False


class BClient():
    def __init__(self, server_address, queue):
        self.server_address = server_address
        self.cqueue = queue
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect(server_address)
        self.running = True

    def run(self):
        try:
            counter = 0
            while self.running:
                data = json.loads(self.socket.recv(1024).strip())
                if data:
                    self.cqueue.put(("msg", data))
                    counter = 0

                    # Send a reply
                    if 'type' in data.keys() and data['type'] != 'ack':
                        reply = {'type': 'ack', 'payload':'ack'}
                        self.socket.sendto(json.dumps(reply), self.server_address)

                else:
                    counter += 1

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


#TODO not used yet
class BBaseMessage:
    def __init__(self, mtype):
        self.message = {}
        self.message['type'] = mtype

    def dump(self):
        return json.dumps(self.message)


class BCommandMessage(BBaseMessage):
    def __init__(self, mtype, payload):
        super(BCommandMessage, self).__init__(mtype)
        self.message['payload'] = payload

####################################


def main(basedir='/bro'):
    logs = Logs()

    d = DBroCtld(logs, basedir)
    d.start()

if __name__ == "__main__":
    main()
