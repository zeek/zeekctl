# Daemon that is based on broker and that establishes a
# hierarchic overlay for command dissemination and
# result collection

import time
import traceback
import logging
import json
import pybroker

from collections import defaultdict
from Queue import Queue
from threading import Thread

from BroControl.broctl import BroCtl
from BroControl.message import BResMsg
from BroControl.message import BCmdMsg

class DBroctlD(Thread):
    def __init__(self, logs, basedir, suffix=None):
        Thread.__init__(self)

        self.logs = logs
        self.squeue = Queue()
        self.basedir = basedir
        self.suffix = suffix
        self.head = False
        self.control_peer = None
        self.outbound = []

        # Stores intermediate results for commands
        self.commands = {}
        self.command_replies = {}
        logging.debug("DBroctld init with suffix " + str(suffix))

        self.running = True

    def init_broker_peer(self):
        # BroCtl
        self.broctl = BroCtl(self.basedir, ui=TermUI(), suffix=self.suffix)
        self.parent_addr = (self.broctl.config.get_head().addr, int(self.broctl.config.get_head().port))
        self.addr = (self.broctl.config.get_local().addr, int(self.broctl.config.get_local().port))
        self.name = self.broctl.config.get_local().name

        # Start broker client
        self.peer = BrokerPeer(self.name, self.squeue, self.addr)
        self.client_thread = Thread(target=self.peer.run)
        self.client_thread.daemon = True
        self.client_thread.start()

        # check if we are the head of the cluster
        if self.parent_addr == self.addr:
            print "  -- we are the broker-root node of the deep cluster"
            self.head = True
        # if we are not the head node connect to predecessor
        else:
            logging.debug("establishing a connection to predecessor " + str(self.parent_addr))
            self.peer.connect(self.parent_addr)

    def init_overlay(self):
        # Install the local node, its cluster nodes, and its peers
        self.broctl.install()
        # Start the peers in the deep cluster recursively
        self.broctl.create_overlay()

    def run(self):
        self.init_broker_peer()
        self.init_overlay()
        while self.running:
            self.recv()
            time.sleep(0.25)

    def stop(self):
        print "exit dbroctld..."
        logging.debug("exit dbroctld")

        # Shutting down the local bro instances
        self.broctl.stop()

        # Cleanup
        self.peer.stop()
        self.running = False

    def connect(self, peer_addr):
        self.peer.connect(peer_addr)

    def forward_res(self, msg):
        self.send_res(msg['for'], msg['payload'])

    def send_cmd(self, cmd):
        msg = BCmdMsg(self.name, self.addr, cmd)
        self.send(msg)

    def send_res(self, cmd, res):
        msg = BResMsg(self.name, self.addr, cmd, res)
        self.peer.send_pred(msg)

    def send(self, msg):
        self.peer.send(msg)

    def noop(self, *args, **kwargs):
        return True

    def recv(self):
        data = None
        if self.squeue.empty():
            return
        (dtype, peer, data) = self.squeue.get()

        if dtype not in ["msg", "peer-connect", "peer-disconnect"]:
            logging.debug("DBroctlD: malformed data type", dtype, "received")
            raise RuntimeError("DBroctlD: malformed data type", dtype, "received")

        #print str(self.addr) + ": dtype " + str(dtype) + ", peer " + str(peer) + ", data " + str(data)
        if dtype == "msg":
            self.handleMessage(peer, data)
        elif dtype == "peer-connect":
            self.handlePeerConnect(peer)
        elif dtype == "peer-disconnect":
            self.handlePeerDisconnect(peer)
        else:
            raise RuntimeError("undefinded message received")

    def handlePeerConnect(self, peer):
        if(peer != "dclient"):
            self.outbound.append(peer)
            logging.debug("peer " + str(peer) + " connected, " + str(len(self.outbound)) + " outbound connections")
            print ("peer " + str(peer) + " connected, " + str(len(self.outbound)) + " outbound connections")
        else:
            self.control_peer = peer
            logging.debug("node " + str(peer) + " established control connection to us")
            print "node " + str(peer) + " established control connection to us"

    def handlePeerDisconnect(self, peer):
        if(peer != "dclient"):
            print "peer", peer, "disconnected"
            if peer in self.outbound:
                logging.debug(" outbound peer " + str(peer) + " disconnected")
                self.outbound.remove(peer)
        else:
            logging.debug(" we lost our control connection to peer " + str(peer))
            print "control peer", peer, "disconnected"
            self.control_peer = None

    # message handling
    def handleMessage(self, peer, msg):
        if 'type' not in msg.keys():
            print("Error: received a msg with no type")
            raise RuntimeError("malformed message received")

        if msg["type"] == "command":
            self.handleCommand(peer, msg)

        elif msg["type"] == "result":
            self.handleResult(peer, msg)

        else:
            print("handleMessage: unknown message type received")
            raise RuntimeError("message type unknown")

    # Handle a command message received from the control console or a
    # predecessor
    def handleCommand(self, peer, msg):
        ocmd = str(msg['payload'])
        (paddr, pport) = peer
        logging.debug("msg " + str(msg) + ", ocmd " + str(ocmd))
        if paddr != self.parent_addr or pport != self.server_port:
            logging.debug("cmd from peer " + str(peer) + " received that is not our parent " + str(self.parent_addr))
        else:
            logging.debug("cmd from our parent " + str(peer) + " received")

        # Distinguish between command and its parameters
        args = ocmd.split(" ")
        cmd = str(args[0])
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

        elif cmd == 'shutdown':
            # Stop all local bro processes
            self.stop()

        else:
            logging.debug("handleCommand: unknown command, ignoring it")

    # Handle result message from a successor
    def handleResult(self, peer, res):
        if 'for' not in res.keys() or 'payload' not in res.keys():
            raise RuntimeError("Received result message with invalid format")

        cmd = str(res['for'])
        result = res['payload']

        logging.debug("received reply for cmd " + str(cmd) + " from peer " + str(peer) + " with result " + str(result))

        if cmd not in self.commands:
            self.commands[cmd] = []

        # TODO we need a timeout mechanism in case peers fail
        if cmd not in self.command_replies:
            raise RuntimeError("cmd " + cmd + " not known")
        self.command_replies[cmd] -= 1

        for entry in res['payload']:
            self.commands[cmd].append(entry)
            logging.debug("  - append entry " + str(entry) + " to results")

        if self.command_replies[cmd] > 0:
            logging.debug("  - we do nothing yet, as we still wait for " + str(self.command_replies[cmd]) + " replies")
            return

        if self.head:
            self.output_result(cmd, result)
            del self.commands[cmd]
            del self.command_replies[cmd]
        else:
            logging.debug("sending result to predecessor")
            self.send_res(cmd, self.commands[cmd])
            del self.commands[cmd]
            del self.command_replies[cmd]

    # process the results returned from broctl
    def processLocalResult(self, cmd, res):
        if cmd not in ["netstats", "peerstatus", "print_id", "status"]:
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

        if self.head and self.command_replies[cmd] == 0:
            logging.debug("no predecessor, so output results")
            self.output_result(cmd, self.commands[cmd])
            if cmd not in self.commands:
                raise RuntimeError("cmd " + cmd + " is not part of command list")
            del self.commands[cmd]
            del self.command_replies[cmd]

        elif not self.outbound:
            rlist = self.commands[cmd]
            logging.debug("send results for cmd " + str(cmd) + " : " + str(rlist))
            self.send_res(cmd, rlist)
            logging.debug("deleting cmd from cache as we have no outbound peer: " + str(cmd))
            del self.commands[cmd]

        else:
            logging.debug("we wait for " + str(cmd) + " results from our successors")
            # TODO add timout to main control loop!

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
                result.append((str(self.addr), str(n), str(r)))
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

    def output_result(self, cmd, res):
        logging.debug("we have gathered all input for cmd " + str(cmd) + ", thus output results")
        print ("   " + str(cmd) + " results:")

        for e in self.commands[cmd]:
            print("    - " + str(e))
        ## when we have a control connection we need to send the results
        self.send_res_control(cmd, self.commands[cmd])

    # Send a result to the control console
    def send_res_control(self, cmd, res):
        if self.control_peer:
            logging.debug(" ** send result to control " + str(res))
            msg = BResMsg(self.name, self.addr, cmd, res)
            self.peer.send_control(msg)


class BrokerPeer:
    def __init__(self, name, squeue, addr):
        self.name = name
        self.running = True
        self.squeue = squeue
        self.outbound = []
        self.inbound = {}
        self.tq = {}
        self.addr = addr

        # broker topic for commands
        self.ctopic = "dbroctld/cmds"
        # broker topic for results
        self.rtopic = "dbroctld/res"
        self.ctrl_topic = "dbroctld/control" + "/" + name

        # Broker endpoint configuration
        self.ep = pybroker.endpoint(name, pybroker.AUTO_PUBLISH)
        self.ep.listen(int(addr[1]), str(addr[0]))
        print "Dbroctld listens on " + str(addr[0]) +  ":" + str(addr[1])

        # Publish topic prefixes
        self.ep.publish(self.ctopic)
        self.ep.publish(self.ctrl_topic)

        # Create message queue for commands and control messages that is the same for all nodes
        self.tq[self.ctopic] = pybroker.message_queue(self.ctopic, self.ep)
        self.tq[self.ctrl_topic] = pybroker.message_queue(self.ctrl_topic, self.ep)

        # We need new topic for this peer and all its direct successors
        prefix = self.rtopic + "/" + self.name #+ "-"+ str(incoming[0].peer_name)
        self.ep.publish(prefix)

        self.tq[prefix] = pybroker.message_queue(prefix, self.ep)

    def connect(self, peer_addr):
        logging.debug("initiating connection to " + str(peer_addr))
        p = self.ep.peer(str(peer_addr[0]), int(peer_addr[1]), 1)

        if not p:
            logging.debug("no broker connection could be established to " + str(peer_addr))
            return

        stat = self.ep.outgoing_connection_status().need_pop()[0]
        if stat.status != pybroker.outgoing_connection_status.tag_established:
            logging.debug("no broker connection could be established to " + str(peer_addr))
            return

        logging.debug("connected to peer " + str(stat.peer_name))
        self.inbound[stat.peer_name] = (peer_addr, p)

    def disconnect_inbound(self):
        for p in self.inbound.values():
            self.ep.unpeer(p[1])
        self.inbound.clear()

    def recv(self):
        # Check incoming and outgoing connections
        self.check_connections()

        # Checking queues
        for q in self.tq.values():
            msg = q.want_pop()
            self.parse_broker_msg(msg)

    def check_connections(self):
        # 1. Checking incoming connections (we are predecessor in the tree)
        incoming = self.ep.incoming_connection_status().want_pop()
        if incoming:
            if incoming[0].status == pybroker.incoming_connection_status.tag_established:
                self.outbound += [incoming[0].peer_name]
                print self.name + ": incoming connection from peer " + str(incoming[0].peer_name)

                # Tell control
                self.squeue.put(("peer-connect", incoming[0].peer_name, None))

                # We need new topic for this peer and all its direct successors
                #prefix = self.rtopic + "/" + self.name #+ "-"+ str(incoming[0].peer_name)
                #self.ep.publish(prefix)
                #self.tq[prefix] = pybroker.message_queue(prefix, self.ep)

            elif incoming[0].status == pybroker.incoming_connection_status.tag_disconnected:
                print self.name + ": peer " + str(incoming[0].peer_name) + " disconnected from us"
                # Tell control
                self.squeue.put(("peer-disconnect", incoming[0].peer_name, None))
                self.outbound.remove(incoming[0].peer_name)

        # 2. Checking outgoing connections
        outgoing = self.ep.outgoing_connection_status().want_pop()
        if outgoing:
            if outgoing[0].status == pybroker.outgoing_connection_status.tag_established:
                logging.debug("peer connected to us: " + outgoing[0].peer_name)
            elif outgoing[0].status == pybroker.outgoing_connection_status.tag_disconnected:
                logging.debug("peer disconnected from us: " + outgoing[0].peer_name)
                del self.inbound[outgoing[0].peer_name]

    def parse_broker_msg(self, msg):
        if not msg:
            return

        for j in msg:
            event = None
            res = []
            for i in j:
                if not event:
                    event = i
                else:
                    res.append(json.loads(str(i)))

            if event:
                peer = str(res[0])
                if (self.name != peer):
                    logging.debug(" received msg from (" + str(peer) + ") " + str(res[2]))
                    self.squeue.put(("msg", res[1], res[2]))

    def run(self):
        while self.running:
            self.recv()
            time.sleep(0.25)

    def send(self, msg):
        if msg.type() == 'command':
            print str(self.name) + ": publish command msg " + str(msg.dump())
            self.ep.send(self.ctopic, msg.dump())
        elif msg.type() == 'result':
            print str(self.name) + ": publish result msg " + str(msg.dump())
            self.ep.send(self.rtopic, msg.dump())
        else:
            raise RuntimeError("no msg type specified")

    def send_succ(self, msg):
        for p in self.outbound.keys():
            prefix = self.ctopic + "/" + self.name + "-" + p
            self.ep.send(prefix, msg.dump())

    def send_pred(self, msg):
        # Send the message to all peers that are connected inbound
        for p in self.inbound.keys():
            prefix = self.rtopic + "/" + p
            self.ep.send(prefix, msg.dump())

    def send_control(self, msg):
        print "publish control msg to " + self.ctrl_topic
        self.ep.send(self.ctrl_topic, msg.dump())

    def stop(self):
        self.disconnect_inbound()
        self.ep.unlisten(0)
        self.running = False


########################################################

class TermUI:
    def __init__(self):
        pass

    def output(self, msg):
        print(msg)
    warn = info = output

    def error(self, msg):
        print("ERROR", msg)

########################################################


class Logs:
    def __init__(self):
        self.store = defaultdict(list)

    def append(self, id, stream, txt):
        self.store[id].append((stream, txt))

    def get(self, id, since=0):
        msgs = self.store.get(id) or []
        return msgs[since:]

def main(basedir='/bro', suffix=None):
    logs = Logs()

    d = DBroctlD(logs, basedir, suffix)
    d.start()

if __name__ == "__main__":
    main()
