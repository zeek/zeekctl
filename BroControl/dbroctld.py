# Daemon that is based on broker and that establishes a
# hierarchic overlay for command dissemination and
# result collection

import traceback
import logging
import time
import pybroker

from collections import defaultdict

from BroControl.broctl import BroCtl
from BroControl.message import BResMsg
from BroControl.message import BCmdMsg
from BroControl.message import BroMsg

from BroControl.daemonbase import BaseDaemon
from BroControl.daemonbase import TermUI
from BroControl.daemonbase import Logs
from BroControl import util


class DBroctlD(BaseDaemon):
    def __init__(self, logs, basedir, suffix=None):
        BaseDaemon.__init__(self)

        self.logs = logs
        self.basedir = basedir
        self.suffix = suffix
        self.head = False
        self.control_peer = None
        self.successors = []
        self.predecessors = []
        self.local_cluster = {}

        # Stores intermediate results for commands
        self.commands = {}
        self.command_replies = {}
        logging.debug("DBroctld init with suffix " + str(suffix))

    def init_all(self):
        self.init_broctl()
        # Install the local node, its cluster nodes, and its peers
        self.broctl.install()
        # Start the peers in the deep cluster recursively
        self.broctl.create_overlay()

    def init_broctl(self):
        # BroCtl
        self.broctl = BroCtl(self.basedir, ui=TermUI(), suffix=self.suffix)
        # Our address
        self.addr = (self.broctl.config.get_local().addr, int(self.broctl.config.get_local().port))
        # The address of our parent in the hierarchy (= our addr if none)
        self.parent_addr = (self.broctl.config.get_head().addr, int(self.broctl.config.get_head().port))

        # What is our name and our cluster-id?
        if(hasattr(self.broctl.config.get_local(), "cluster")):
            self.name= self.broctl.config.get_local().cluster
        else:
            self.name= self.broctl.config.get_local().name
        print "init broker_peer with " + self.name

        # Broker topic for communication with client app
        self.ctrl_topic = "dbroctld/control/res/"
        # Broker topic for commands
        self.cmd_topic = "dbroctld/cmds/"
        # Broker topic for results
        self.res_topic = "dbroctld/res/"

        # Topic to send requests to local bros
        self.bro_ctrl_topic = "bro/event/control/" + str(self.name) + "/request/"
        # Topic to obtain responses from local bro
        self.bro_res_topic = "bro/event/control/" + str(self.name) + "/response/"

        # Topics for BrokerPeer
        self.pub = [    self.ctrl_topic + str(self.name),
                        self.bro_ctrl_topic ]

        self.sub_single = [ self.bro_res_topic ]

        self.sub_multi  = [ self.ctrl_topic + str(self.name),
                            self.cmd_topic,
                            self.res_topic + str(self.name) ]

        # Topics that need to be translated to another topics
        # (required to prevent loops)
        #self.forw = { "bro/global/" + self.name + "/" : "dbroctld/event/" }

        # Init the broker peer
        self.init_broker_peer(self.name, self.addr, self.pub, self.sub_single, self.sub_multi)

        # check if we are the head of the cluster
        if self.parent_addr == self.addr:
            print "  -- we are the broker-root node of the deep cluster"
            self.head = True
        # if we are not the head node connect to predecessor
        else:
            logging.debug("establishing a connection to predecessor " + str(self.parent_addr))
            self.peer.connect(self.parent_addr)

    # Initiate broker connections to all bro processes
    # in the local cluster
    def init_bro_connections(self):
        #raise RuntimeError("epic fail")
        node_list = None
        if self.broctl.config.nodes("standalone"):
            node_list = "standalone"
        elif self.broctl.config.nodes("manager"):
            node_list = "cluster"
        nodes = self.broctl.config.nodes(node_list)

        print "connect to local cluster of size " + str(len(nodes)) + ":"

        # Connnect all bros via broker
        for n in nodes:
            addr = (util.scope_addr(n.addr), n.getPort())
            print " - connect to " + n.name + "-bro at " + str(addr)
            self.peer.connect(addr)

        for n in nodes:
            self.local_cluster[n.name] = n

    # disconnect from all bro processes via broker
    def disconnect_bro_connections(self):
        for k in self.local_cluster.keys():
            self.peer.disconnect(k)

    def stop(self):
        print "exit dbroctld..."
        logging.debug("exit dbroctld")

        # Shutting down the local Bro instances
        self.broctl.stop()

        # Cleanup
        self.peer.stop()
        self.running = False

    def send_cmd(self, cmd):
        msg = BCmdMsg(self.name, self.addr, cmd)
        self.send(self.cmd_topic, msg)

    def send_res(self, cmd, res):
        msg = BResMsg(self.name, self.addr, cmd, res)
        for p in self.predecessors:
            topic = self.res_topic + str(p)
            logging.debug(" - send results to predecessor " + str(p) + " via topic " + topic)
            self.send(topic, msg)

    # Send a result to the control console
    def send_res_control(self, cmd, res):
        if self.control_peer:
            logging.debug(" ** send results to control " + str(res))
            msg = BResMsg(self.name, self.addr, cmd, res)
            self.peer.send(self.ctrl_topic, msg)

    def forward_res(self, msg):
        self.send_res(msg['for'], msg['payload'])

    def handle_timeout(self, (timeout, msg)):
        logging.debug("handle_timeout: " + timeout)

        if timeout == "init_bro_connections":
            logging.debug("timeout: init_bro_connections received")
            self.init_bro_connections()
        elif timeout == "command_timeout":
            logging.debug("timeout: command_timeout received")
            if (msg in self.commands) and self.head:
                self.output_result(msg, self.commands[msg])
                del self.commands[msg]
                del self.command_replies[msg]
            # FIXME add handling of results for an intermediate node here
        else:
            logging.debug("unhandled timeout " + timeout + " received with " + msg)

    def handle_peer_connect(self, peer, direction):
        if(peer == "dclient"):
            self.control_peer = peer
            logging.debug("control connection opened")
            print "node " + str(peer) + " established control connection to us"
            return

        # If peer connected inbound to broker peer it means that it is a
        # successor in the tree or a bro running in a local cluster
        if direction == "inbound":
            if peer in self.local_cluster:
                logging.debug("Bro-peer " + str(peer) + " connected outbound")
                print "Bro " + str(peer) + " connected to us"
            else:
                self.successors.append(peer)
                logging.debug("peer " + str(peer) + " connected, " + str(len(self.successors)) + " outbound connections")
                print ("Peer " + str(peer) + " connected, " + str(len(self.successors)) + " outbound connections")

        # Outbound means that we connected to this peer,
        elif direction == "outbound":
            # We connected to a bro peer
            if peer in self.local_cluster:
                logging.debug("Bro-peer " + str(peer) + " connected outbound")
                print "Bro " + str(peer) + " connected to us"
            # it is thus a predecessor in the hierarchy
            else:
                self.predecessors.append(peer)
                logging.debug("Peer " + str(peer) + " connected, " + str(len(self.predecessors)) + " outbound connections")
                print ("Peer " + str(peer) + " connected, " + str(len(self.predecessors)) + " outbound connections")
                # Publish results to this peer
                self.peer.publish_topic(self.res_topic + "/" + str(peer))

    def handle_peer_disconnect(self, peer, direction):
        if peer == "dclient":
            logging.debug(" we lost our control connection to peer " + str(peer))
            print "control peer", peer, "disconnected"
            self.control_peer = None
            return

        print "peer", peer, "disconnected, " + str(direction)
        if direction == "inbound":
            if peer in self.local_cluster:
                logging.debug("Bro " + str(peer) + " disconnected")
            elif peer in self.successors:
                logging.debug("Successor " + str(peer) + " disconnected")
                self.successors.remove(peer)
        elif direction == "outbound":
            if peer in self.predecessors:
                logging.debug("Predecessor " + str(peer) + " disconnected")
                self.predecessors.remove(peer)

    # message handling
    def handle_message(self, mtype, peer, msg):
        if mtype not in ["msg", "peer-connect", "peer-disconnect"]:
            logging.debug("DBroctlD: malformed data type", mtype, "received")
            raise RuntimeError("DBroctlD: malformed data type", mtype, "received")

        #  print str(self.addr) + ": dtype " + str(dtype) + ", peer " + str(peer) + ", data " + str(data)
        if mtype == "peer-connect":
            self.handle_peer_connect(peer, msg)

        elif mtype == "peer-disconnect":
            self.handle_peer_disconnect(peer, msg)

        elif mtype == "msg":
            if 'type' not in msg.keys():
                print("Error: received a msg with no type")
                raise RuntimeError("malformed message received")

            if msg["type"] == "command":
                self.handle_command(peer, msg)

            elif msg["type"] == "result":
                self.handle_results(peer, msg['for'], msg['payload'])

        else:
            raise RuntimeError("undefinded message received")

    # Handle a command message received from the control console or a
    # predecessor
    def handle_command(self, peer, msg):
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

        if cmd == "netstats":
            self.netstats()
        elif cmd == "peerstatus":
            self.peerstatus()
        elif hasattr(func,  'api_exposed'):
            res = None

            try:
                res = func(*args)
            except Exception:
                res = traceback.format_exc()

            # handle the result of the command
            self.handle_results(self.name, cmd, res)

        # Post processing of commands
        self.cmd_post_processing(cmd)

    # Handle result message from a successor
    def handle_results(self, peer, cmd, res):
        logging.debug("handle_result for peer " + str(peer) + ", cmd " + str(cmd) + ", res " + str(res))
        if cmd not in ["netstats", "peerstatus", "print_id", "status", "Control::net_stats_response", "Control::peer_status_response"] or not res:
            return

        if(peer == self.name): # Results obtained locally
            logging.debug("result of cmd " + str(cmd) + " is " + str(res))
            # Do command specific formatting of results and store them
            self.add_command(cmd, len(self.successors))
            self.commands[cmd] = self.format_results(cmd, res)

        else: # Results received from peer
            if str(cmd) not in self.command_replies or cmd not in self.commands:
                raise RuntimeError("cmd " + cmd + " not known")

            logging.debug("received reply for cmd " + str(cmd) + " from peer " + str(peer) + " with result " + str(res))
            self.command_replies[cmd] -= 1
            for entry in res:
                logging.debug("  - append entry " + str(entry) + " to results")
                self.commands[cmd].append(entry)

        # We have all results together
        if self.command_replies[cmd] == 0:
            if self.head: #  output results as we are the head
                self.output_result(cmd, self.commands[cmd])
            else: #  send results to predecessor
                logging.debug("sending result to predecessor")
                self.send_res(cmd, self.commands[cmd])

            del self.commands[cmd]
            del self.command_replies[cmd]
            # Cancel timeout for this command
            self.cancel_timeout(("command_timeout", cmd))
        elif self.command_replies[cmd] < 0:
            raise RuntimeError("something went wrong here")

    def cmd_post_processing(self, cmd):
        # Certain commands require additional action afterwards
        if cmd == 'start':  # Start bros
            self.schedule_timeout(time.time() + 5, "init_bro_connections")
            pass
        elif cmd == 'shutdown':  # Stop all local bro processes
            self.stop()

    def format_results(self, cmd, res):
        if not res:
            return [(None, None, None)]
        elif(cmd == "status"):
            return self.format_results_status(res)
        elif(cmd == "print_id"):
            return self.format_results_printid(res)
        else:
            result = []
            for (n, v, r) in res.get_node_output():
                logging.debug(" - " + str(n) + " : " + str(v) + " : " + str(r))
                result.append((str(self.addr), str(n), str(r)))
            return result

    def format_results_status(self, res):
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

    def format_results_printid(self, res):
        result = []
        for (node, success, args) in res.get_node_output():
            if success:
                logging.debug("printid gave success, args " + str(args))
                result.append("" + str(node) + ": " + str(args))
                # result.append("%12s   %s = %s" % (node, args[0], args[1]))
            else:
                result.append("%12s   <error: %s>" % (node, args))
        return result

    def output_result(self, cmd, res):
        logging.debug("we have gathered all input for cmd " + str(cmd) + ", thus output results")
        print ("   " + str(cmd) + " results:")

        for e in self.commands[cmd]:
            print("    - " + str(e))
        # when we have a control connection we need to send the results
        self.send_res_control(cmd, self.commands[cmd])

    def netstats(self):
        """

        Queries each of the nodes for their current counts of captured and
        dropped packets."""

        # store that we issued this command to wait for replies
        self.add_command("Control::net_stats_response", len(self.local_cluster) + len(self.successors))
        # Construct the broker msg to send
        msg = BroMsg("Control::net_stats_request", None)
        self.send(self.bro_ctrl_topic, msg)
        # eventlist += [(node, "Control::net_stats_request", [], "Control::net_stats_response")]

    def peerstatus(self):
        """

        Queries each of the nodes for their current counts of captured and
        dropped packets."""

        # store that we issued this command to wait for replies
        self.add_command("Control::peer_status_response", len(self.local_cluster) + len(self.successors))
        # Construct the broker msg to send
        msg = BroMsg("Control::peer_status_request", None)
        self.send(self.bro_ctrl_topic, msg)

    def add_command(self, cmd, count):
        self.commands[cmd] = []
        self.command_replies[cmd] = count
        logging.debug("dbroctld" + cmd + ", expect at least " + str(count) + " replies")


def main(basedir='/bro', suffix=None):
    #pybroker.report_init()
    logs = Logs()

    d = DBroctlD(logs, basedir, suffix)
    d.start()

if __name__ == "__main__":
    main()
