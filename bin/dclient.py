#! /usr/bin/env python

import socket
import sys
import time
import cmd
import errno
import json

class BClient(cmd.Cmd):
    prompt = '[BClient] > '

    def __init__(self, host, port):
        cmd.Cmd.__init__(self)
        if host and port:
            self.connect(host, port)
        self.sock = None

    def connect(self, host, port):
        if host and port:
            self.host = host
            self.port = port
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock.setblocking(False)
        else:
            raise RuntimeError("connect not possible")

    def send_receive(self, data):
        if not self.sock:
            print "not connected to a dbroctld daemon yet"
            return

        self.send(data)

        while data:
            try:
                data = json.loads(self.sock.recv(1024).strip())
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

        data = {'type': 'command', 'payload': data}
        try:
            self.sock.sendall(json.dumps(data))
        finally:
            pass

    def finish(self):
        if self.sock:
            self.sock.close()

    # cmdloop handlers
    def do_connect(self, line):
        """ connect [hostname] [port] """
        host, port = line.split()
        self.connect(host, int(port))
        print "connected..."

    def do_start(self, line):
        """ start the bro instances in the deep cluster """
        print "starting bro instances of deep cluster..."
        self.send_receive("start")

    def do_stop(self, line):
        """ stop the bro instances in the deep cluster """
        print "stopping bro instances of deep cluster..."
        self.send_receive("stop")

    def do_shutdown(self, line):
        """ shutdown the deep cluster """
        print "shutting down deep cluster..."
        self.send_receive("shutdown")

    def do_disconnect(self, line):
        """ shutdown the deep cluster and disconnect """
        if self.sock:
            self.do_shutdown()
        self.finish()

    def do_exit(self, line):
        """ exit client """
        self.finish()
        sys.exit()

    def do_status(self, line):
        """ gives status """
        if self.sock:
            print "connected to host " + str(self.host) + "::" + str(self.port)
        else:
            print "not connected yet"



def main(argv):
    client = BClient(None, None)
    client.cmdloop()

if __name__ == "__main__":
    main(sys.argv[1:])
