#! /usr/bin/env python

import socket
import sys
import time
import cmd
import errno
import json
import os
from Queue import Queue
from threading import Thread

control_port = 4242
d_host = "localhost"
d_port = 9990
delay_response = 10


class BClient(cmd.Cmd):
    intro = 'Deep Cluster Client'
    prompt = '[BClient] > '
    ruler = '-'

    def __init__(self, host, port):
        cmd.Cmd.__init__(self)
        if host and port:
            self.connect(host, port)

        self.host = None
        self.port = None

        self.sock = None
        self.cq = Queue()
        self.bc = BConnector(self.cq)
        self.client_thread = Thread(target=self.bc.run)
        self.client_thread.daemon = True
        self.client_thread.start()

    def con(self):
        self.bc.connect(d_host, d_port)

    def do_cl(self, line):
        """ connect to localhost on 9990 """
        print "connect to localhost on 9990"
        self.bc.connect("192.168.4.239", 9990)

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
        else:
            print ("not connected yet")

    def do_disconnect(self, line):
        """ shutdown the deep cluster and disconnect """
        self.bc.disconnect()

    def do_exit(self, line):
        """ exit client """
        self.bc.finish()
        return True

    def do_dstatus(self, line):
        """ gives local status """
        if self.bc.is_connected():
            print "connected to host " + str(self.host) + "::" + str(self.port)
        else:
            print ("not connected yet")

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

    def preloop(self):
        os.system('clear')

    def precmd(self, line):
        return line

    def postcmd(self, stop, line):
        # print "line " + str(line) + " stop " + str(stop)
        if not self.bc.is_connected() or not line:
            return stop
        for l in ["connect", "disconnect", "shutdown", "cl", "dstatus"]:
            if l in line:
                return stop

        counter = 0
        data = None
        while counter < (delay_response / 0.25):
            time.sleep(0.25)
            while not self.cq.empty():
                data = self.cq.get()
                self.handleResult(data, line)
                break
            if data:
                break
            counter += 1
        return stop

    def handleResult(self, data, line):
        if "netstats" in line or "peerstatus" in line:
            print ""
            print "-----------------------------------------------------------"
            print "response | "
            for (n,v,w) in data:
                print "         | " + str(n) + ", " + str(v) + ", " + str(w)
            print "-----------------------------------------------------------"
            print ""
        else:
            print "-----------------------------------------------------------"
            print "response | " + str(data)
            print "-----------------------------------------------------------"
            print ""

class BConnector():
    def __init__(self, cqueue):
        self.running = True
        self.host = None
        self.port = None
        self.sock = None
        self.cq = cqueue

    def connect(self, host, port):
        if host and port:
            self.host = host
            self.port = port
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.sock.bind(("127.0.0.1", control_port))
                self.sock.connect((self.host, self.port))
            except socket.error:
                print "Couldnt connect to ", str(host), (port), " check parameters"
                return
        else:
            print ("no host or no port specified")

    def send(self, data):
        if not self.sock:
            print "not connected to a dbroctld daemon yet"
            return

        sdata = {'type': 'command', 'payload': data}
        try:
            self.sock.sendall(json.dumps(sdata))
        finally:
            pass

    def run(self):
        while self.running:
            if self.sock:
                try:
                    data = None
                    data_socket = self.sock.recv(4096).strip()
                    if data_socket:
                        data = json.loads(data_socket)
                    if data:
                        if 'payload' in data.keys():
                            # print "response: " + str(data["payload"])
                            self.cq.put(data['payload'])

                except socket.error, e:
                    err = e.args[0]
                    if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                        break
                    else:
                        print e
                        sys.exit(1)

            time.sleep(0.1)

    def disconnect(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def is_connected(self):
        return self.sock is not None

    def finish(self):
        self.running = False
        if self.sock:
            self.sock.close()


def main(argv):
    client = BClient(None, None)
    client.cmdloop()

if __name__ == "__main__":
    main(sys.argv[1:])
