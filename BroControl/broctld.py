from BroControl import version
from BroControl.broctl import BroCtl
from BroControl.ser import dumps
import os
import bottle
import json

class TermUI:
    def __init__(self):
        pass

    def info(self, msg):
        print(msg)
    warn = info

    def error(self, msg):
        print("ERROR", msg)


app = bottle.Bottle(autojson=False)
app.install(bottle.JSONPlugin(json_dumps=dumps))

@app.hook('before_request')
def before_request():
    if not hasattr(bottle.local, 'b'):
        bottle.local.b = BroCtl(ui=TermUI())

@app.route('/exec/:cmd')
def exec_(cmd):
    result = bottle.local.b.execute(cmd)
    return {"result": result}

@app.post('/:cmd')
def cmd(cmd):
    func = getattr(bottle.local.b, cmd)
    result = {"result": func()}
    return result

def main():
    bottle.run(app, host='localhost', port=8082)

if __name__ == "__main__":
    main()
