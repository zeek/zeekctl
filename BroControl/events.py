import time
import logging

from BroControl import config
from BroControl import util

try:
    import broccoli
except ImportError:
    broccoli = None

try:
    import pybroker
    broker = True
except ImportError:
    broker = False


# Broker communication with running nodes.

# Sends event to a set of nodes in parallel.
#
# events is a list of tuples of the form (node, event, args, result_event).
#   node:    the destination node.
#   event:   the name of the event to send (node that receiver must subscribe
#            to it as well).
#   args:    a list of event args; each arg must be a data type understood by
#            the Broccoli module.
#   result_event: name of a event the node sends back. None if no event is
#                 sent back.
#
# Returns a list of tuples (node, success, results_args).
#   If success is True, result_args is a list of arguments as shipped with the
#   result event, or [] if no result_event was specified.
#   If success is False, results_args is a string with an error message.
def send_events_parallel(events):
    results = []

    for (node, event, args, result_event) in events:
        logging.debug("check event " + str(event))

        (success, result_args) = _send_event_broker(node, event, args, result_event)
        if success and result_args:
            results += [(node, success, result_args)]
        else:
            logging.debug("local cmd failed")
            results += [(node, success, "cmd failed")]

    return results

def _send_event_broker(node, event, args, result_event):
    host = util.scope_addr(node.addr)

    ep = pybroker.endpoint("control", pybroker.AUTO_PUBLISH)
    logging.debug("initiating broker peering with " + str(host) + ":" + str(node.getPort()))
    ep.peer(host, node.getPort(), 1)

    logging.debug("broker: %s(%s) to node %s", event, ", ".join(args), node.name)
    logging.debug("args is " + str(args))
    time.sleep(1)

    stat = ep.outgoing_connection_status().need_pop()[0]
    if stat.status != pybroker.outgoing_connection_status.tag_established:
        logging.debug("no broker connection could be established to " + str(stat.peer_name))
        return

    logging.debug("connected to broker-peer " + str(stat.peer_name))

    ep.advertise("bro/event/control/response/")
    rqueue = pybroker.message_queue("bro/event/control/response/", ep)
    logging.debug("broker connect to host " + str(host) + ", port " + str(node.getPort()))
    ep.publish("bro/event/control/request/")

    # Construct the broker event to send
    vec = pybroker.vector_of_data(1, pybroker.data(event))
    for a in args:
        vec.append(pybroker.data(str(a)))
    # Send the event to the broker endpoint
    ep.send("bro/event/control/request/", vec)

    resp_event = None
    res = []
    # timeout of at most 4 seconds for retrieving the reply
    for c in range(0, 6):
        time.sleep(0.5)
        logging.debug("receiving broker content, counter " + str(c))
        msg = rqueue.want_pop()
        if msg:
            for i in pybroker.deque_of_message(msg):
                for j in i:
                    if not resp_event:
                        resp_event = j
                    else:
                        res.append(str(j).strip())
                    logging.debug("broker data is " + str(res))

        if resp_event:
            break

    if resp_event:
        if not res:
            logging.debug("broker event " + str(resp_event) + " without payload received")
        else:
            logging.debug("broker event " + str(resp_event) + " received with payload " + str(res))
        return (True, res)
    else:
        logging.debug("broker: no response obtained")
        return (False, "no response obtained")
