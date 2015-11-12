#! /usr/bin/env python

import socket
import sys
import time
import cmd
import errno
import json
import os
import pybroker
from Queue import Queue
from threading import Thread

control_port = 4242
d_host = "localhost"
d_port = 9990
delay_response = 15

class BClient(cmd.Cmd):
    intro = 'Deep Cluster Client'
    prompt = '[BClient] > '
    ruler = '-'

    def __init__(self, host, port):
        cmd.Cmd.__init__(self)

        if host:
            self.host = host
        else:
            self.host = d_host

        if port:
            self.port = port
        else:
            self.port = d_port

        self.cq = Queue()
        self.bc = BPeer(self.cq)
        self.client_thread = Thread(target=self.bc.run)
        self.client_thread.daemon = True
        self.client_thread.start()

        if host and port:
            self.bc.connect(host, port)

    def do_cl(self, line):
        """ connect to stored node """
        self.bc.connect(self.host, self.port)

    # cmdloop handlers
    def do_connect(self, line):
        """ connect [hostname] [port] """
        linelist = line.split()
        if len(linelist) != 2:
            print("required: connect [hostname] [port]")
            return

        host, port = linelist
        self.host = host
        self.port = port
        self.bc.connect(host, int(port))

    def do_start(self, line):
        """ start the bro instances in the deep cluster """
        if self.bc.is_connected():
            print "starting bro instances of deep cluster..."
            self.bc.send("start")
        else:
            print ("not connected yet")

    def do_stop(self, line):
        """ stop the bro instances in the deep cluster """
        if self.bc.is_connected():
            print "stopping bro instances of deep cluster..."
            self.bc.send("stop")
        else:
            print ("not connected yet")

    def do_shutdown(self, line):
        """ shutdown the deep cluster """
        if self.bc.is_connected():
            print "shutting down deep cluster..."
            self.bc.send("shutdown")
            self.bc.disconnect()
            self.bc.stop()
            return True
        else:
            print ("not connected yet")

    def do_disconnect(self, line):
        """ shutdown the deep cluster and disconnect """
        self.bc.disconnect()

    def do_exit(self, line):
        """ exit client """
        self.bc.stop()
        return True

    def do_dstatus(self, line):
        """ gives local status """
        if self.bc.is_connected():
            print "connected to host " + str(self.host) + "::" + str(self.port)
        else:
            print ("not connected yet, stored information: " + str(self.host) + " " + str(self.port) )

    def do_status(self, line):
        """ sends out status command to connected dbroctld"""
        if self.bc.is_connected():
            print "send status command to dbroctld"
            self.bc.send("status")
        else:
            print ("not connected yet")

    def do_netstats(self, line):
        """ sends out the netstats command """
        if self.bc.is_connected():
            print "obtaining netstats information from all bros"
            self.bc.send("netstats")
        else:
            print ("not connected yet")

    def do_peerstatus(self, line):
        """ sends out the peerstatus command """
        if self.bc.is_connected():
            print "obtaining peerstatus information from all bros"
            self.bc.send("peerstatus")
        else:
            print ("not connected yet")

    def do_print_id(self, line):
        """ sends out the print_id command """
        linelist = line.split()
        if len(linelist) != 1:
            print("required: print [id]")
            return

        args = ""
        for i in linelist:
            args += str(i) + " "

        if self.bc.is_connected():
            self.bc.send("print_id " + args.strip())
            print "obtaining peer_id information from all bros"
        else:
            print ("not connected yet")

    def do_clear(self, line):
        """ clears the console """
        os.system('clear')

    def preloop(self):
        os.system('clear')

    def precmd(self, line):
        return line

    def postcmd(self, stop, line):
        #print "line " + str(line) + " stop " + str(stop)
        if not self.bc.is_connected() or not line:
            return stop
        for l in ["connect", "disconnect", "shutdown", "cl", "connect_local", "dstatus", "help", "exit", "start", "stop"]:
            if l in line:
                return stop

        counter = 0
        msg = None
        while counter < (delay_response / 0.25):
            time.sleep(0.25)
            while not self.cq.empty():
                msg = self.cq.get()
                self.handleResult(msg, line)
                break
            if msg:
                break
            counter += 1
        return stop

    def handleResult(self, msg, line):
        data = msg[2]['payload']
        if "netstats" in line or "peerstatus" in line:
            print ""
            print "-------------------------------------------------------------------------------"
            for (n,v,w) in data:
                print "" + str(n) + ", " + str(v) + ", " + str(w)
            print "-------------------------------------------------------------------------------"
            print ""
        elif "print_id" in line:
            print ""
            print "-------------------------------------------------------------------------------"
            for n in data:
                print "" + str(n)
            print "-------------------------------------------------------------------------------"
            print ""
        elif "status" in line:
            print ""
            print "-------------------------------------------------------------------------------"
            for n in data:
                print "" + str(n)
            print "-------------------------------------------------------------------------------"
            print ""
        else:
            print ""
            print "-----------------------------------------------------------"
            print str(data)
            print "-----------------------------------------------------------"
            print ""


class BPeer:
    def __init__(self, cqueue):
        self.name = "dclient"
        self.addr = ("127.0.0.1", 4242)
        self.cqueue = cqueue
        self.peered = None
        self.control_peer = None
        self.running = True

        # Broker stuff
        self.ep = pybroker.endpoint(self.name, pybroker.AUTO_PUBLISH)
        self.ctrltopic = "dbroctld/control"
        self.ctopic = "dbroctld/cmds"
        self.ep.publish(self.ctrltopic)
        self.mq = pybroker.message_queue(self.ctrltopic, self.ep)

    def connect(self, addr, port):
        # Connect to broker peer
        self.peered = self.ep.peer(str(addr), int(port), 1)

        if not self.peered:
            print("no broker connection could be established to " + str(addr))
            return

        stat = self.ep.outgoing_connection_status().need_pop()[0]
        if stat.status != pybroker.outgoing_connection_status.tag_established:
            print("no broker connection could be established to " + str(addr))
            return

        print "connected to peer " + str(stat.peer_name)
        self.control_peer = stat.peer_name

    def disconnect(self):
        if self.peered:
            self.ep.unpeer(self.peered)
            self.peered = None
            self.mq = None
            self.ep.unpublish(self.ctrltopic)

    def is_connected(self):
        return self.peered != None

    def run(self):
        while self.running:
            if self.mq:
                msg = self.mq.want_pop()
                self.parse_broker_msg(msg)
            time.sleep(0.25)

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
                    self.cqueue.put(("msg", peer, res[2]))

    def send(self, data):
        msg = BCmdMsg(self.name, self.addr, data)
        self.ep.send(self.ctopic, msg.dump())

    def stop(self):
        self.disconnect()
        self.running = False


class BBaseMsg(object):
    def __init__(self, mtype):
        self.message = {}
        self.message['type'] = mtype
        self.name = None
        self.addr = None

    def type(self):
        return self.message['type']

    def dump(self):
        vec = pybroker.vector_of_data(1, pybroker.data("dbroctld"))
        vec.append(pybroker.data(str((json.dumps(self.name)))))
        vec.append(pybroker.data(str((json.dumps(self.addr)))))
        vec.append(pybroker.data(str(json.dumps(self.message))))
        return vec


class BCmdMsg(BBaseMsg):
    def __init__(self, name, addr, payload):
        super(BCmdMsg, self).__init__("command")
        self.message['payload'] = payload
        self.name = name
        self.addr = addr


def main(argv):
    client = None
    if len(argv) == 2:
        client = BClient(argv[0], argv[1])
    else:
        client = BClient(None, None)
    client.cmdloop()

if __name__ == "__main__":
    main(sys.argv[1:])
