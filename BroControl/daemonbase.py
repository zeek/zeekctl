# Stub class for a daemon: BrokerControl
# Basic Broker Connector: BrokerPeer
# + helper classes Logs and TermUI

import pybroker
import logging
import time
import json
from collections import defaultdict
from Queue import Queue
from threading import Thread

from message import BResMsg

# Polling interval for new messages
loop_time = 0.25


class BaseDaemon(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.squeue = Queue()
        self.fes = {}
        self.peer = None
        self.running = True

    # Put functionality to connect to BrokerPeer here
    def init_broker_peer(self, name, addr, pub, sub_single, sub_multi):
        # Start broker client
        self.peer = BrokerPeer(name, addr, self.squeue, pub, sub_single, sub_multi)
        self.client_thread = Thread(target=self.peer.run)
        self.client_thread.daemon = True
        self.client_thread.start()

    def init_all(self):
        pass

    def run(self):
        self.init_all()
        while self.running:
            self.recv()
            self.check_timeout()
            time.sleep(loop_time)

    def recv(self):
        data = None
        if self.squeue.empty():
            return
        (mtype, peer, data) = self.squeue.get()
        self.handle_message(mtype, peer, data)

    # Timeout handling
    def check_timeout(self):
        if len(self.fes) == 0:
            return
        t = sorted(self.fes).pop()
        if t <= time.time():
            for e in self.fes[t]:
                self.handle_timeout(e)
            del self.fes[t]

    def handle_peer_connect(self, peer, direction):
        pass

    def handle_peer_disconnect(self, peer, direction):
        pass

    def handle_message(self, mytpe, peer, msg):
        pass

    def handle_timeout(self, (timeout, msg)):
        pass

    # Schedule a timeout for myself
    def schedule_timeout(self, time, ttype, msg=None):
        if time not in self.fes:
            self.fes[time] = [(ttype, msg)]
        else:
            self.fes[time] += [(ttype, msg)]

    # Cancel timeout
    def cancel_timeout(self, timeout):
        cand = None
        for c in self.fes:
            if self.fes[c] == timeout:
                cand = c
                break
        if cand:
            del self.fes[cand]

    def connect(self, peer_addr):
        if not self.peer:
            raise RuntimeError("Not connected to BrokerPeer yet")
        self.peer.connect(peer_addr)

    def send(self, topic, msg):
        if not self.peer:
            raise RuntimeError("Not connected to BrokerPeer yet")
        self.peer.send(topic, msg)

    def stop(self):
        self.running = False
        if self.peer:
            self.peer.stop()

    def noop(self, *args, **kwargs):
        return True

class TermUI:
    def __init__(self):
        pass

    def output(self, msg):
        print(msg)
    warn = info = output

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



class BrokerPeer:
    def __init__(self, name, addr, squeue, pub, sub_single, sub_multi):
        self.name = name
        self.running = True
        self.squeue = squeue
        self.outbound = {}
        self.inbound = []
        self.tq = {}
        self.addr = addr
        #self.fq = {}

        # Broker endpoint configuration
        flags = pybroker.AUTO_PUBLISH | pybroker.AUTO_ADVERTISE | pybroker.AUTO_ROUTING
        self.ep = pybroker.endpoint(name, flags)
        if self.addr:
            self.ep.listen(int(addr[1]), str(addr[0]))
            print "Dbroctld listens on " + str(addr[0]) + ":" + str(addr[1])

        # Publications
        for p in pub:
            self.ep.publish(p)

        # Subscriptions
        for s in sub_single:
            self.tq[s] = pybroker.message_queue(s, self.ep, pybroker.SINGLE_HOP)
        for s in sub_multi:
            self.tq[s] = pybroker.message_queue(s, self.ep, pybroker.MULTI_HOP)

        # Forwarding of topics
        # - receiving msgs
        #for f in forw.keys():
        #    self.fq[f] = (pybroker.message_queue(f, self.ep, pybroker.MULTI_HOP), forw[f])
        # - resending messages
        #for f in forw.values():
        #    self.ep.publish(f)


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
        self.outbound[stat.peer_name] = (peer_addr, p)
        self.squeue.put(("peer-connect", stat.peer_name, "outbound"))

    def disconnect(self, peer_name):
        if str(peer_name) in self.outbound:
            self.ep.unpeer(self.outbound[str(peer_name)][1])
            del self.outbound[peer_name]

    def disconnect_all(self):
        for p in self.outbound.values():
            self.ep.unpeer(p[1])
        self.outbound.clear()

    def is_connected(self):
        return len(self.outbound) > 0

    def recv(self):
        # Check incoming and outgoing connections
        self.check_connections()

        # Checking queues
        for q in self.tq.values():
            msg = q.want_pop()
            self.parse_broker_msg(msg)
        #for q in self.fq.values():
        #    msg = q[0].want_pop()
        #    if msg:
        #        self.send(q[1], msg)

    def check_connections(self):
        # 1. Checking incoming connections (other peer initiated connection)
        incoming = self.ep.incoming_connection_status().want_pop()
        if incoming:
            if incoming[0].status == pybroker.incoming_connection_status.tag_established:
                self.inbound += [incoming[0].peer_name]
                logging.debug("incoming connection from peer " + str(incoming[0].peer_name))

                # Tell control
                self.squeue.put(("peer-connect", incoming[0].peer_name, "inbound"))

            elif incoming[0].status == pybroker.incoming_connection_status.tag_disconnected:
                logging.debug("peer " + str(incoming[0].peer_name) + " disconnected from us")
                # Tell control
                self.squeue.put(("peer-disconnect", incoming[0].peer_name, "inbound"))
                self.inbound.remove(incoming[0].peer_name)

        # 2. Checking outgoing connections (we initiated connection)
        outgoing = self.ep.outgoing_connection_status().want_pop()
        if outgoing:
            if outgoing[0].status == pybroker.outgoing_connection_status.tag_established:
                logging.debug("peer connected to us: " + outgoing[0].peer_name)
                self.squeue.put(("peer-connect", outgoing[0].peer_name, "outbound"))
            elif outgoing[0].status == pybroker.outgoing_connection_status.tag_disconnected:
                logging.debug("peer disconnected from us: " + outgoing[0].peer_name)
                self.squeue.put(("peer-disconnect", outgoing[0].peer_name, "outbound"))
                if outgoing[0].peer_name in self.outbound:
                    del self.outbound[outgoing[0].peer_name]

    def parse_broker_msg(self, msg):
        if not msg:
            return

        json_encoding = True
        for j in msg:
            event = None
            res = []
            for i in j:
                if not event:
                    event = i
                else:
                    # We need to differentiate input from another daemon (json)
                    # from input coming from a bro process (non-json)
                    try:
                        res.append(json.loads(str(i)))
                    except ValueError:
                        res.append(str(i).strip())
                        json_encoding = False

            if not event:
                return

            if json_encoding: # msg from another BrokerPeer endpoint
                peer = str(res[0])
                if (self.name != peer):
                    logging.debug(" received msg from (" + str(peer) + ") " + str(res[2]))
                    self.squeue.put(("msg", res[1], res[2]))
            else: # msg from a bro process
                logging.debug(" received msg from bro for event" + str(event) + " with res" + str(res))
                msg = BResMsg(None, None, str(event), res)
                self.squeue.put(("msg", None, msg.json()))

    def run(self):
        while self.running:
            self.recv()
            time.sleep(0.25)

    def send(self, topic, msg):
        logging.debug(str(self.name) + ": send msg " + msg.str() + " to " + str(topic))
        self.ep.send(topic, msg.dump())

    def subscribe_topic(self, topic):
        if topic not in self.tq:
            self.tq[topic] = pybroker.message_queue(topic, self.ep, pybroker.MULTI_HOP)

    def unsubscribe_topic(self, topic):
        if topic in self.tq:
            del self.tq[topic]

    def publish_topic(self, topic):
        self.ep.publish(topic)

    def unpublish_topic(self, topic):
        self.ep.unpublish(topic)

    def stop(self):
        self.disconnect_all()
        #self.ep.unlisten(0)
        self.running = False
