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


# Broccoli/Broker communication with running nodes.

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
    if config.Config.use_broker():
        return send_events_parallel_broker(events)
    else:
        return send_events_parallel_broccoli(events)

def send_events_parallel_broccoli(events):
    results = []
    sent = []

    for (node, event, args, result_event) in events:

        if not broccoli:
            results += [(node, False, "no Python bindings for Broccoli installed")]
            continue

        (success, bc) = _send_event_init_broccoli(node, event, args, result_event)
        if success and result_event:
            sent += [(node, result_event, bc)]
        else:
            results += [(node, success, bc)]

    for (node, result_event, bc) in sent:
        (success, result_args) = _send_event_wait_broccoli(node, result_event, bc)
        results += [(node, success, result_args)]

    return results

def _send_event_init_broccoli(node, event, args, result_event):
    host = util.scope_addr(node.addr)

    try:
        bc = broccoli.Connection("%s:%d" % (host, node.getPort()), broclass="control",
                        flags=broccoli.BRO_CFLAG_ALWAYS_QUEUE, connect=False)
        bc.subscribe(result_event, _event_callback(bc))
        bc.got_result = False
        bc.connect()
    except IOError as e:
        logging.debug("broccoli: cannot connect to node %s", node.name)
        return (False, str(e))

    logging.debug("broccoli: %s(%s) to node %s", event, ", ".join(args), node.name)
    bc.send(event, *args)

    return (True, bc)

def send_events_parallel_broker(events):
    logging.debug("send_events_parallel: use broker")
    results = []
    sent = []

    for (node, event, args, result_event) in events:
        logging.debug("check event " + str(event))
        if not broker:
            logging.debug("send_events_parallel_broker: no Python bindings for Broker")
            results += [(node, False, "no Python bindings for Broker installed")]
            continue

        (success, result_args) = _send_event_broker(node, event, args, result_event)
        if success and result_args:
            results += [(node, success, result_args)]
        else:
            logging.debug("local cmd failed")
            results += [(node, success, "cmd failed")]

    return results

def _send_event_broker(node, event, args, result_event):
    host = util.scope_addr(node.addr)

    ep = pybroker.endpoint("broctl", pybroker.AUTO_PUBLISH)
    ep.peer(host, node.getPort(), 1)
    ep.advertise("/bro/event/cluster/control/response")

    logging.debug("broker: %s(%s) to node %s", event, ", ".join(args), node.name)
    time.sleep(1)

    oq = ep.outgoing_connection_status()
    inter = oq.want_pop()
    if not inter:
        logging.debug("no broker connection could be established")
        return(False, "no broker connection could be established")

    rqueue = pybroker.message_queue("/bro/event/cluster/control/response", ep)
    ep.publish("/bro/event/cluster/control/request")

    vec = pybroker.vector_of_data(1, pybroker.data(event))
    ep.send("/bro/event/cluster/control/request", vec)

    msg = None
    resp = None
    # timeout of at most 3 seconds
    time.sleep(1)
    for c in range(0,2):
        msg = rqueue.want_pop()
        if msg:
            for i in pybroker.deque_of_message(msg):
                for j in i:
                    resp = str(j).strip()
        if resp:
            break
        time.sleep(1)

    if msg:
        logging.debug("broker: " + str(event) + " resp " + str(resp))
        return (True, resp)
    else:
        logging.debug("broker: no response obtained")
        return (False, "no response obtained")

def _send_event_wait_broccoli(node, result_event, bc):
    # Wait until we have sent the event out.
    cnt = 0
    while bc.processInput():
        time.sleep(1)

        cnt += 1
        if cnt > int(config.Config.commtimeout):
            logging.debug("broccoli: timeout during send to node %s", node.name)
            return (False, "time-out")

    if not result_event:
        return (True, [])

    # Wait for reply event.
    cnt = 0
    bc.processInput()
    while not bc.got_result:
        time.sleep(1)
        bc.processInput()

        cnt += 1
        if cnt > int(config.Config.commtimeout):
            logging.debug("broccoli: timeout during receive from node %s", node.name)
            return (False, "time-out")

    logging.debug("broccoli: %s(%s) from node %s", result_event, ", ".join(bc.result_args), node.name)
    return (True, bc.result_args)


def _event_callback(bc):
    def save_results(*args):
        bc.got_result = True
        bc.result_args = args
    return save_results

