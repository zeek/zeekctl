#! /usr/bin/env python

import sys
import time
import cmd
import os
from Queue import Queue
from threading import Thread

sys.path.insert(0, "@PREFIX@/lib/broctl")

from BroControl.daemonbase import BrokerPeer
from BroControl.message import BCmdMsg

control_port = 4242
d_host = "localhost"
d_port = 9990
delay_response = 15


class DeepClient(cmd.Cmd):
    intro = 'Deep Cluster Client'
    prompt = '[BClient] > '
    ruler = '-'

    def __init__(self, name, host, port):
        cmd.Cmd.__init__(self)

        self.name = name
        if host:
            local_host = host
        else:
            local_host = d_host

        if port:
            local_port = port
        else:
            local_port = d_port

        self.addr = (local_host, local_port)

        self.ctrl_topic = "dbroctld/control/"
        self.cmd_topic = "dbroctld/cmds/"

        # pack topics for BrokerPeer
        sub_single = []
        sub_multi = [self.ctrl_topic + "res"]
        pub = [self.cmd_topic]

        self.cq = Queue()
        self.peer = BrokerPeer("dclient", None, self.cq, pub, sub_single, sub_multi)
        self.client_thread = Thread(target=self.peer.run)
        self.client_thread.daemon = True
        self.client_thread.start()

        if host and port:
            self.peer.connect(self.addr)

    def send_cmd(self, cmd):
        if self.peer.is_connected():
            msg = BCmdMsg(self.name, self.addr, cmd)
            self.peer.send(self.cmd_topic, msg)
            return True
        else:
            print "not connected yet"
            return False

    def do_cl(self, line):
        """ connect to stored node """
        self.peer.connect(self.addr)

    # cmdloop handlers
    def do_connect(self, line):
        """ connect [hostname] [port] """
        linelist = line.split()
        if len(linelist) != 2:
            print("required: connect [hostname] [port]")
            return

        host, port = linelist
        self.addr= (host, port)
        self.peer.connect(self.addr)

    def do_start(self, line):
        """ start the bro instances in the deep cluster """
        if self.send_cmd("start"):
            print "starting bro instances of deep cluster..."

    def do_stop(self, line):
        """ stop the bro instances in the deep cluster """
        if self.send_cmd("stop"):
            print "stopping bro instances of deep cluster..."

    def do_shutdown(self, line):
        """ shutdown the deep cluster """
        if self.send_cmd("shutdown"):
            print "shutting down deep cluster..."
            self.peer.disconnect_all()
            self.peer.stop()
            return True

    def do_disconnect(self, line):
        """ shutdown the deep cluster and disconnect """
        self.peer.disconnect()

    def do_exit(self, line):
        """ exit client """
        self.peer.stop()
        return True

    def do_dstatus(self, line):
        """ gives local status """
        if self.peer.is_connected():
            print "connected to host " + str(self.addr[0]) + "::" + str(self.addr[1])
        else:
            print ("not connected yet, stored information: " + str(self.addr[0]) + " " + str(self.addr[1]) )

    def do_status(self, line):
        """ sends out status command to connected dbroctld"""
        if self.send_cmd("status"):
            print "send status command to dbroctld"

    def do_netstats(self, line):
        """ sends out the netstats command """
        if self.send_cmd("netstats"):
            print "obtaining netstats information from all bros"

    def do_peerstatus(self, line):
        """ sends out the peerstatus command """
        if self.send_cmd("peerstatus"):
            print "obtaining peerstatus information from all bros"

    def do_print_id(self, line):
        """ sends out the print_id command """
        linelist = line.split()
        if len(linelist) != 1:
            print("required: print [id]")
            return

        args = ""
        for i in linelist:
            args += str(i) + " "

        if self.send_cmd("print_id " + args.strip()):
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
        if not self.peer.is_connected() or not line:
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
                self.handle_result(msg, line)
            if line in str(msg):
                break
            counter += 1
        return stop

    def handle_result(self, msg, line):
        # Ignore all connection-related messages
        for s in ["peer-connect", "peer-disconnect"]:
            if s in msg:
                return

        # Format all other responses
        data = msg[2]['payload']
        #if "netstats" in line or "peerstatus" in line:
        if "netstats" in line or "peerstatus" in line:
            print ""
            print "-------------------------------------------------------------------------------"
            for n in data:
                print str(n)
            print "-------------------------------------------------------------------------------"
            print ""
        #elif "peerstatus" in line:
        #    print ""
        #    print "-------------------------------------------------------------------------------"
        #    for (n,v,w) in data:
        #        print "" + str(n) + ", " + str(v) + ", " + str(w)
        #    print "-------------------------------------------------------------------------------"
        #    print ""
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


def main(argv):
    #pybroker.report_init()
    client = None
    if len(argv) == 2:
        client = DeepClient("dclient", argv[0], argv[1])
    else:
        client = DeepClient(None, None)
    client.cmdloop()

if __name__ == "__main__":
    main(sys.argv[1:])
