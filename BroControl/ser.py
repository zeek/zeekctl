import json
from json import dumps as json_dumps, loads

from BroControl import node

class MyJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, node.Node):
            return obj.to_dict()
        return json.JSONEncoder.default(self, obj)

def dumps(obj):
    return json.dumps(obj, cls=MyJsonEncoder)
