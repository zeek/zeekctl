# Basic Broker Connector
# + helper classes Logs and TermUI

import pybroker
import logging
import time
import json

from Queue import Queue


class BrokerPeer:
    def __init__(self, name, addr, squeue,  pub, sub):
        self.name = name
        self.running = True
        self.squeue = squeue
        self.outbound = {}
        self.inbound = []
        self.tq = {}
        self.addr = addr

        # Broker endpoint configuration
        self.ep = pybroker.endpoint(name, pybroker.AUTO_ADVERTISE | pybroker.AUTO_PUBLISH)
        if self.addr:
            self.ep.listen(int(addr[1]), str(addr[0]))
            print "Dbroctld listens on " + str(addr[0]) + ":" + str(addr[1])

        # Publications
        for p in pub:
            self.ep.publish(p)

        # Subscriptions
        for s in sub:
            self.tq[s] = pybroker.message_queue(s, self.ep)

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

    def disconnect(self):
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

    def check_connections(self):
        # 1. Checking incoming connections (other peer initiated connection)
        incoming = self.ep.incoming_connection_status().want_pop()
        if incoming:
            if incoming[0].status == pybroker.incoming_connection_status.tag_established:
                self.inbound += [incoming[0].peer_name]
                print self.name + ": incoming connection from peer " + str(incoming[0].peer_name)

                # Tell control
                self.squeue.put(("peer-connect", incoming[0].peer_name, "inbound"))

            elif incoming[0].status == pybroker.incoming_connection_status.tag_disconnected:
                print self.name + ": peer " + str(incoming[0].peer_name) + " disconnected from us"
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
                del self.outbound[outgoing[0].peer_name]

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

    def send(self, topic, msg):
        logging.debug(str(self.name) + ": send msg " + msg.str() + " to " + str(topic))
        self.ep.send(topic, msg.dump())

    def subscribe_topic(self, topic):
        if topic not in self.tq:
            self.tq[topic] = pybroker.message_queue(topic, self.ep)

    def unsubscribe_topic(self, topic):
        if topic in self.tq:
            del self.tq[topic]

    def publish_topic(self, topic):
        self.ep.publish(topic)

    def unpublish_topic(self, topic):
        self.ep.unpublish(topic)

    def stop(self):
        self.disconnect()
        self.ep.unlisten(0)
        self.running = False
