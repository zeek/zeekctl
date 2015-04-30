#! /usr/bin/env python

import socket
import sys
import time
import cmd
import errno

class BClient(cmd.Cmd):
    prompt = '[BClient] > '

    def __init__(self, host, port):
        cmd.Cmd.__init__(self)
        if host and port:
            self.connect(host, port)

    def connect(self, host, port):
        if host and port:
            self.host = host
            self.port = port
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock.setblocking(False)
        else:
            raise RuntimeError("connect not possible")

    def sendAndReceiveData(self, data):
        self.sendData(data)
        while data:
            try:
                data = self.sock.recv(1024).strip()
                print "response:", data
            except socket.error, e:
                err = e.args[0]
                if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                    break
                else:
                    print e
                    sys.exit(1)
            time.sleep(0.1)


    def sendData(self, data):
        print "data to send: ", data
        try:
            self.sock.sendall(data)
        finally:
            pass

    def finish(self):
        print "closing socket"
        self.sock.close()

    # cmdloop handlers
    def do_connect(self, line):
        """ connect [hostname] [port] """
        host, port = line.split()
        self.connect(host, int(port))

    def do_send_receive(self, data):
        self.sendAndReceiveData(data)

    def do_send(self,data):
        self.sendData(data)

    def do_disconnect(self, line):
        self.finish()

    def do_exit(self, line):
        self.finish()
        sys.exit()


def main(argv):
    client = BClient(None, None)
    client.cmdloop()
    #client.sendAndReceiveData(data)
    client.finish()

if __name__ == "__main__":
    main(sys.argv[1:])
