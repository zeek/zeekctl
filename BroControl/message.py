# Message classes that are used by dbroctld for
# the communication in between different instances

import json
import pybroker


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

    def str(self):
        return str(self.message)


class BCmdMsg(BBaseMsg):
    def __init__(self, name, addr, payload):
        super(BCmdMsg, self).__init__("command")
        self.message['payload'] = payload
        self.name = name
        self.addr = addr


class BResMsg(BBaseMsg):
    def __init__(self, name, addr, cmd, payload):
        super(BResMsg, self).__init__(mtype="result")
        self.name = name
        self.addr = addr
        self.message['for'] = cmd
        self.message['payload'] = payload
