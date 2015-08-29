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

# Global options
# TODO need to be moved to options.py
peer_timeout = 50
polling_interval = 0.2
# source port of the dclient connecting to dbroctld
control_port = 4242


class DBroCtld(Thread):
    def __init__(self, logs, basedir, suffix=None):
        Thread.__init__(self)

        self.logs = logs
        self.running = True
        self.squeue = Queue()
        self.outbound = []
        self.basedir = basedir
        self.suffix = suffix
        self.head = False
        self.control_peer = None

        # Stores intermediate results for commands
        self.commands = {}
        self.command_replies = {}
        logging.debug("DBroctld init with suffix " + str(suffix))

    def init_server(self):
        # BroCtl
        self.broctl = BroCtl(self.basedir, ui=TermUI(), suffix=self.suffix)
        self.parent_address = self.broctl.config.get_head().addr
        self.parent_port = int(self.broctl.config.get_head().port)
        self.server_address = self.broctl.config.get_local().addr
        self.server_port = int(self.broctl.config.get_local().port)

        # SocketServer
        print "starting dbroctld... "
        print "  -- dbroctld listens on", self.server_address, "::", self.server_port
        self.bserver = BSocketServer(self.squeue, (self.server_address, self.server_port), BSocketHandler, bind_and_activate=True)
        self.server_thread = Thread(target=self.bserver.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.daemon_threads = True
        self.server_thread.start()
        logging.debug("DBroctlD SocketServer started")

        # Client only if we are not the root node of the hierarchy
        self.bclient = None
        if (self.parent_address != self.server_address or self.parent_port != self.server_port):
            self.bclient = BClient((self.parent_address, self.parent_port), self.squeue)
            self.client_thread = Thread(target=self.bclient.run)
            self.client_thread.daemon = True
            self.client_thread.start()
            logging.debug("DClient started, parent is " + str(self.parent_address) + ", " + str(self.parent_port))
            print ("  -- dclient started, parent is " + str(self.parent_address) + ", " + str(self.parent_port))
        else:
            print "  -- we are the root node of the deep cluster"
            self.head = True

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
        (dtype, peer, data) = self.squeue.get()
        (addr, port) = peer
        logging.debug("dtype: " + str(dtype) + " with data: " + str(data) + " from peer " + str(addr))

        if dtype not in ["msg", "peer-connect", "peer-disconnect"]:
            logging.debug("DBroctlD: malformed data type", dtype, "received")
            raise RuntimeError("DBroctlD: malformed data type", dtype, "received")

        if dtype == "msg":
            self.handleMessage(peer, data)

        elif dtype == "peer-connect":
            self.handlePeerConnect(peer)

        elif dtype == "peer-disconnect":
            self.handlePeerDisconnect(peer)

    # Handle a received message
    def handleMessage(self, peer, msg):
        (addr, port) = peer
        logging.debug("handleMessage: msg " + str(msg) + " from peer " + str(addr) + " received")

        if 'type' not in msg.keys():
            logging.debug("Error: received a msg with no type")
            raise RuntimeError("malformed message received")

        if msg["type"] == "command":
            self.handleCommand(peer, msg)

        elif msg["type"] == "ack":
            logging.debug("Acknowledgement received")

        elif msg["type"] == "result":
            self.handleResult(peer, msg)

        else:
            logging.debug("handleMessage: unknown message type received")
            raise RuntimeError("message type unknown")

    # Handle a command message received from the control console or a
    # predecessor
    def handleCommand(self, peer, msg):
        ocmd = str(msg['payload'])
        (paddr, pport) = peer
        logging.debug("msg " + str(msg) + ", ocmd " + str(ocmd))
        if paddr != self.parent_address or pport != self.server_port:
            logging.debug("cmd from peer " + str(peer) + " received that is not our parent " + str(self.parent_address))
        else:
            logging.debug("cmd from our parent " + str(peer) + " received")

        # Distinguish between command and its parameters
        args = ocmd.split(" ")
        cmd = args[0]
        args.remove(cmd)

        logging.debug("executing cmd " + str(cmd) + " with args " + str(args))
        if args:
            print("execute cmd " + str(cmd) + " with args " + str(args))
        else:
            print("execute cmd " + str(cmd))
        # Execute command...
        func = getattr(self.broctl, cmd, self.noop)

        if hasattr(func,  'api_exposed'):
            res = None

            try:
                res = func(*args)
            except Exception:
                res = traceback.format_exc()

            # handle the result of the command
            self.processLocalResult(cmd, res)

            # Forward command ...
            self.forwardCommand(ocmd)

        elif cmd == 'shutdown':
            # Forward command ...
            self.forwardCommand(cmd)
            # Stop all local bro processes
            self.stop()

        else:
            logging.debug("handleCommand: unknown command, ignoring it")

    # process the results returned from broctl
    def processLocalResult(self, cmd, res):
        if cmd not in ["netstats", "peerstatus", "print_id", "status"]:
            self.sendResultToControl(cmd, "ack")
            return

        if res:
            logging.debug("result of cmd " + str(cmd) + " is " + str(res))
        else:
            logging.debug("no result for cmd " + str(cmd))
            return

        if cmd in self.commands:
            raise RuntimeError("old netstats results available!")

        # Do command specific formatting of results and store them
        self.commands[cmd] = self.process_local_result_cmd(cmd, res)
        self.command_replies[cmd] = len(self.outbound)

        if not self.bclient and not self.outbound:
            logging.debug("no bclient, so output results")
            self.output_result(cmd, self.commands[cmd])
            if cmd not in self.commands:
                raise RuntimeError("cmd " + cmd + " is not part of command list")
            del self.commands[cmd]
            del self.command_replies[cmd]

        elif not self.outbound:
            rlist = self.commands[cmd]
            logging.debug("send results for cmd " + str(cmd) + " : " + str(rlist))
            self.sendResult(cmd, rlist)
            logging.debug("deleting cmd from cache as we have not outbound peer: " + str(cmd))
            del self.commands[cmd]

        else:
            logging.debug("we wait for " + str(cmd) + " results from our successors")

    def process_local_result_cmd(self, cmd, res):
        if not res:
            return [(None, None, None)]
        elif(cmd == "status"):
            return self.process_local_result_cmd_status(res)
        elif(cmd == "print_id"):
            return self.process_local_result_cmd_printid(res)
        else:
            result = []
            for (n, v, r) in res.get_node_output():
                logging.debug(" - " + str(n) + " : " + str(v) + " : " + str(r))
                result.append((str(self.server_address), str(n), str(r)))
            return result

    def process_local_result_cmd_status(self, res):
        result = []
        roleswidth = 20
        hostwidth = 13
        data = res.get_node_data()
        showall = "peers" in data[0][2]
        if showall:
            colfmt = "{name:<12} {roles:<{0}} {host:<{1}} {status:<9} {pid:<6} {peers:<6} {started}"
        else:
            colfmt = "{name:<12} {roles:<{0}} {host:<{1}} {status:<9} {pid:<6} {started}"

        hdrlist = ["name", "roles", "host", "status", "pid", "peers", "started"]
        header = dict((x, x.title()) for x in hdrlist)
        result.append(colfmt.format(roleswidth, hostwidth, **header))

        colfmtstopped = "{name:<12} {roles:<{0}} {host:<{1}} {status}"

        for r in res.get_node_data():
            node_info = r[2]
            if node_info["pid"]:
                mycolfmt = colfmt
            else:
                mycolfmt = colfmtstopped

            result.append(mycolfmt.format(roleswidth, hostwidth, **node_info))
            # add an empty line
            result.append("")

        return result

    def process_local_result_cmd_printid(self, res):
        result = []
        for (node, success, args) in res.get_node_output():
            if success:
                logging.debug("printid gave success, args " + str(args))
                result.append("" + str(node) + ": " + str(args))
                #result.append("%12s   %s = %s" % (node, args[0], args[1]))
            else:
                result.append("%12s   <error: %s>" % (node, args))
        return result

    # Handle result message from a successor
    def handleResult(self, peer, res):
        if 'for' not in res.keys() or 'payload' not in res.keys():
            raise RuntimeError("Received result message with invalid format")

        cmd = res['for']
        result = res['payload']

        logging.debug("received reply for cmd " + str(cmd) + " from peer " + str(peer) + " with result " + str(result))

        if cmd not in self.commands:
            raise RuntimeError(str(cmd) + " not contained in list of locally issued commands")

        # TODO we need a timeout mechanism in case peers fail
        self.command_replies[cmd] -= 1

        for entry in res['payload']:
            self.commands[cmd].append(entry)
            logging.debug("  - append entry " + str(entry) + " to results")

        if self.command_replies[cmd] > 0:
            logging.debug("  - we do nothing yet, as we still wait for " + str(self.command_replies[cmd]) + " replies")
            return

        if not self.bclient:
            self.output_result(cmd, result)
            del self.commands[cmd]
            del self.command_replies[cmd]
        else:
            logging.debug("sending result to bclient")
            self.sendResult(cmd, self.commands[cmd])
            del self.commands[cmd]
            del self.command_replies[cmd]

    def output_result(self, cmd, res):
        logging.debug("we have gathered all input for cmd " + str(cmd) + ", thus output results")
        print ("   " + str(cmd) + " results:")

        for e in self.commands[cmd]:
            print("    - " + str(e))
        ## when we have a control connection we need to send the results
        self.sendResultToControl(cmd, self.commands[cmd])

    def handlePeerConnect(self, peer):
        (paddr, pport) = peer
        if(pport != control_port):
            self.outbound.append(peer)
            logging.debug("peer " + str(peer) + " connected, " + str(len(self.outbound)) + " outbound connections")
            print ("peer " + str(peer) + " connected, " + str(len(self.outbound)) + " outbound connections")
        else:
            self.control_peer = peer
            logging.debug("node" + str(peer) + " established control connection to us")
            print "node" + str(peer) + " established control connection to us"

    def handlePeerDisconnect(self, peer):
        (paddr, pport) = peer
        if(pport != control_port):
            print "peer", peer, "disconnected"
            if peer in self.outbound:
                logging.debug(" outbound peer " + str(peer) + " disconnected")
                self.outbound.remove(peer)
        else:
            logging.debug(" we lost our control connection to peer " + str(peer))
            print "control peer", peer, "disconnected"

    # Forward command to all successors
    def forwardCommand(self, cmd):
        if self.outbound:
            logging.debug("forward cmd \"" + str(cmd) + "\" to ")
        else:
            logging.debug("no successor to forward cmd to")

        for peer in self.outbound:
            logging.debug(" - " + str(peer))
            print("  - forward \"" + str(cmd) + "\" to peer" + str(peer))
            self.sendCommand(peer, cmd)

    # Send a command to a peer
    def sendCommand(self, peer, cmd):
        msg = BCmdMsg(cmd)
        self.bserver.send(peer, msg)

    # Send a result to the control console
    def sendResultToControl(self, cmd, res):
        if self.control_peer:
            logging.debug(" ** send result to control " + str(res))
            msg = BResMsg(cmd, res)
            self.bserver.send(self.control_peer, msg)

    # Send a result to our predecessor
    def sendResult(self, cmd, res):
        if not self.bclient:
            logging.debug("no inbound connection to send to")
            raise RuntimeError("no inbound connection to send to")

        msg = BResMsg(cmd, res)
        self.bclient.send(msg)

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
        self.squeue.put(("peer-connect", peer, None))

    def peer_disconnected(self, peer):
        logging.debug("Peer disconnected: " + str(peer))
        self.outbound.pop(peer)
        self.squeue.put(("peer-disconnect", peer, None))

    def receive_data(self, peer, data):
        self.squeue.put(("msg", peer, data))

    def send(self, peer, msg):
        if peer in self.outbound:
            self.outbound[peer].send(msg)

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
                data = self.request.recv(4096).strip()
                if data != "":
                    data = json.loads(data)
                    counter = 0
                    logging.debug("Handler for peer " + str(self.client_address) + " received data: " + str(data))

                    self.server.receive_data(self.client_address, data)

                    # Stop the handler if we receive a shutdown command
                    if 'type' in data.keys() and data['type'] == 'command':
                        if data['payload'] == 'shutdown':
                            self.stop()

                else:
                    counter += 1

                if counter >= (peer_timeout / polling_interval):
                    break

                # Go to sleep
                time.sleep(polling_interval)

        finally:
            self.stop()

    def send(self, msg):
        self.request.sendto(msg.dump(), self.client_address)

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
                    self.cqueue.put(("msg", self.server_address, data))
                    counter = 0
                else:
                    counter += 1

                if counter >= (peer_timeout / polling_interval):
                    break

            # Go to sleep
            time.sleep(polling_interval)

        finally:
            self.finish()

    def send(self, msg):
        logging.debug("bclient send msg to " + str(self.server_address))
        self.socket.sendto(msg.dump(), self.server_address)

    def finish(self):
        self.socket.close()

    def stop(self):
        self.finish()
        self.running = False


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
# Message declarations


class BBaseMsg(object):
    def __init__(self, mtype):
        self.message = {}
        self.message['type'] = mtype

    def dump(self):
        return json.dumps(self.message)


class BCmdMsg(BBaseMsg):
    def __init__(self, payload):
        super(BCmdMsg, self).__init__("command")
        self.message['payload'] = payload


class BResMsg(BBaseMsg):
    def __init__(self, cmd, payload):
        super(BResMsg, self).__init__(mtype="result")
        self.message['for'] = cmd
        self.message['payload'] = payload
####################################


def main(basedir='/bro', suffix=None):
    logs = Logs()

    d = DBroCtld(logs, basedir, suffix)
    d.start()

if __name__ == "__main__":
    main()
