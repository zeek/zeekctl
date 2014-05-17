from BroControl.broctld import Client
from BroControl.ser import dumps
from bottle import Bottle, run
import json

app = Bottle(autojson=False)
ontrol.node.Node

class MyJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return str(obj.strftime("%Y-%m-%d %H:%M:%S"))
        return json.JSONEncoder.default(self, obj)

#app.install(bottle.JSONPlugin(json_dumps=lambda s: json.dumps(s, cls=MyJsonEncoder)))
app.install(bottle.JSONPlugin(json_dumps=lambda s: json.dumps(s, default=dumps)))

@app.route('/start')
def start():
    i = app.daemon.call("start")
    return {"id": i} 

@app.route('/stop')
def start():
    i = app.daemon.call("stop")
    return {"id": i} 

@app.route('/status')
def status():
    s = app.daemon.sync_call("status")
    return {"result": s}

@app.route('/time')
def time():
    return app.daemon.sync_call("time")

@app.route('/exec/:cmd')
def start(cmd):
    i = app.daemon.call("execute", cmd)
    return {"id": i} 

@app.route('/result/:id')
def result(id):
    id = int(id)
    return {"result": app.daemon.getresult(id)}

@app.route('/log/:id')
@app.route('/log/:id/:since')
def result(id, since=0):
    id = int(id)
    since = int(since)
    return {"log": app.daemon.getlog(id, since) or []}

def main():
    app.daemon = Client('ipc:///bro/socket')
    run(app, host='localhost', port=8082)

if __name__ == "__main__":
    main()
