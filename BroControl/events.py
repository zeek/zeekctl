import time
import logging

from BroControl import config
from BroControl import util

try:
    import broccoli
except ImportError:
    broccoli = None


# Broccoli communication with running nodes.

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
    sent = []

    for (node, event, args, result_event) in events:

        if not broccoli:
            results += [(node, False, "no Python bindings for Broccoli installed")]
            continue

        success, bc = _send_event_init(node, event, args, result_event)
        if success and result_event:
            sent += [(node, result_event, bc)]
        else:
            results += [(node, success, bc)]

    for (node, result_event, bc) in sent:
        success, result_args = _send_event_wait(node, result_event, bc)
        bc.connDelete()
        results += [(node, success, result_args)]

    return results

def _send_event_init(node, event, args, result_event):

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

def _send_event_wait(node, result_event, bc):
    # Wait until we have sent the event out.
    cnt = 0
    while bc.processInput():
        time.sleep(1)

        cnt += 1
        if cnt > config.Config.commtimeout:
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
        if cnt > config.Config.commtimeout:
            logging.debug("broccoli: timeout during receive from node %s", node.name)
            return (False, "time-out")

    logging.debug("broccoli: %s(%s) from node %s", result_event, ", ".join(bc.result_args), node.name)
    return (True, bc.result_args)

def _event_callback(bc):
    def save_results(*args):
        bc.got_result = True
        bc.result_args = args
    return save_results

