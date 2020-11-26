#!/usr/bin/env python3
import sys
import requests
import time
import pprint
import json

def log(id, last):
    res = requests.get("http://localhost:8082/log/%d/%d" % (id, last)).json()
    if not res['log']:
        sys.stdout.write("waiting...\r")
        sys.stdout.flush()
        return last

    for rec in res['log']:
        print ' '.join(rec), '                '
    return last+len(res['log'])

def wait(id):
    print "Waiting for job %d to finish" % id
    last = 0
    while True:
        res = requests.get("http://localhost:8082/result/%d" % id).json()
        last = log(id, last)
        if res['result'] is not None:
            return json.loads(res['result'])
        time.sleep(.2)


def run(action):
    res = requests.get("http://localhost:8082/%s" % action).json()
    print(wait(res['id']))

def call(action):
    out = requests.get("http://localhost:8082/%s" % action).text
    try:
        return json.loads(out)
    except:
        return out

if __name__ == "__main__":
    if sys.argv[1] == 'bg':
        print call(sys.argv[2])
    else:
        run(sys.argv[1])
