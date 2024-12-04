#!/usr/bin/env python3
import json
import pprint
import sys
import time

import requests


def log(id, last):
    res = requests.get(f"http://localhost:8082/log/{id}/{last}").json()
    if not res["log"]:
        sys.stdout.write("waiting...\r")
        sys.stdout.flush()
        return last

    for rec in res["log"]:
        print(" ".join(rec), "                ")
    return last + len(res["log"])


def wait(id):
    print(f"Waiting for job {id} to finish")
    last = 0
    while True:
        res = requests.get(f"http://localhost:8082/result/{id}").json()
        last = log(id, last)
        if res["result"] is not None:
            return json.loads(res["result"])
        time.sleep(0.2)


def run(action):
    res = requests.get(f"http://localhost:8082/{action}").json()
    print(wait(res["id"]))


def call(action):
    out = requests.get(f"http://localhost:8082/{action}").text
    try:
        return json.loads(out)
    except:
        return out


if __name__ == "__main__":
    if sys.argv[1] == "bg":
        print(call(sys.argv[2]))
    else:
        run(sys.argv[1])
