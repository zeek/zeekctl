import json

from ZeekControl import node
from ZeekControl import cmdresult

class MyJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, node.Node):
            return obj.to_dict()
        if isinstance(obj, cmdresult.CmdResult):
            return obj.to_dict()
        return json.JSONEncoder.default(self, obj)

def dumps(obj):
    return json.dumps(obj, cls=MyJsonEncoder)
