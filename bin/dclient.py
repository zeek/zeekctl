#! /usr/bin/env python

import socket
import sys
import time
import cmd
import errno
import json

control_port=4242
d_host="localhost"
d_port=9990

class BClient(cmd.Cmd):
    prompt = '[BClient] > '

    def __init__(self, host, port):
        cmd.Cmd.__init__(self)
        if host and port:
            self.connect(host, port)
        self.sock = None

    def con(self):
        self.connect(d_host, d_port)

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
            print "connected..."
        else:
            print ("no host or no port specified")

    def send_receive(self, data):
        if not self.sock:
            print "not connected to a dbroctld daemon yet"
            return

        self.send(data)
        while data:
            try:
                data_r = self.sock.recv(1024).strip()
                if data_r:
                    data = json.loads(data_r)
                    if "payload" in data.keys():
                        print "response: " + str(data["payload"])
                    else:
                        print "weird response: " + str(data)
            except socket.error, e:
                err = e.args[0]
                if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                    break
                else:
                    print e
                    sys.exit(1)
            time.sleep(0.1)

    def send(self, data):
        if not self.sock:
            print "not connected to a dbroctld daemon yet"
            return

        sdata = {'type': 'command', 'payload': data}
        try:
            self.sock.sendall(json.dumps(sdata))
        finally:
            pass

    def finish(self):
        if self.sock:
            self.sock.close()

    # cmdloop handlers
    def do_connect(self, line):
        """ connect [hostname] [port] """
        linelist = line.split()
        if len(linelist) != 2:
            print("required: connect [hostname] [port]")
            return

        host, port = linelist
        self.connect(host, int(port))

    def do_start(self, line):
        """ start the bro instances in the deep cluster """
        if self.sock:
            print "starting bro instances of deep cluster..."
            self.send("start")
        else:
            print ("not connected yet")

    def do_stop(self, line):
        """ stop the bro instances in the deep cluster """
        if self.sock:
            print "stopping bro instances of deep cluster..."
            self.send("stop")
        else:
            print ("not connected yet")

    def do_shutdown(self, line):
        """ shutdown the deep cluster """
        if self.sock:
            print "shutting down deep cluster..."
            self.send("shutdown")
            time.sleep(1)
            self.sock.close()
            self.sock = None
        else:
            print ("not connected yet")

    def do_disconnect(self, line):
        """ shutdown the deep cluster and disconnect """
        if self.sock:
            self.sock.close()

    def do_exit(self, line):
        """ exit client """
        if self.sock:
            self.do_shutdown()
        return True

    def do_dstatus(self, line):
        """ gives local status """
        if self.sock:
            print "connected to host " + str(self.host) + "::" + str(self.port)
        else:
            print ("not connected yet")

    def do_status(self, line):
        """ sends out status command to connected dbroctld"""
        if self.sock:
            print "send status command to dbroctld"
        self.send("status")

    def do_netstats(self, line):
        """ sends out the netstats command """
        if self.sock:
            print "obtaining netstats information from all bros"
        self.send("netstats")

    def do_peerstatus(self, line):
        """ sends out the peerstatus command """
        if self.sock:
            print "obtaining peerstatus information from all bros"
        self.send("peerstatus")

    def do_print_id(self, line):
        """ sends out the print_id command """
        linelist = line.split()
        if len(linelist) != 1:
            print("required: print [id]")
            return

        args = ""
        for i in linelist:
            args += str(i) + " "

        if self.sock:
            self.send("print_id " + args.strip())
            print "obtaining peer_id information from all bros"
        else:
            print ("not connected yet")

def main(argv):
    client = BClient(None, None)
    client.cmdloop()

if __name__ == "__main__":
    main(sys.argv[1:])
