import logging

from ZeekControl import config

errmsg = ""

try:
    import broker
    import broker.zeek
except ImportError as e:
    broker = None
    errmsg = e

# Broker communication with running nodes.

# Sends event to a set of nodes in parallel.
#
# events is a list of tuples of the form (node, event, args, result_event).
#   node:    the destination node.
#   event:   the name of the event to send (node that receiver must subscribe
#            to it as well).
#   args:    a list of event args; each arg must be a data type understood by
#            the Broker module.
#   result_event: name of a event the node sends back. None if no event is
#                 sent back.
#
# Returns a list of tuples (node, success, results_args).
#   If success is True, result_args is a list of arguments as shipped with the
#   result event, or [] if no result_event was specified.
#   If success is False, results_args is a string with an error message.

def send_events_parallel(events, topic):

    results = []
    sent = []

    for (node, event, args, result_event) in events:

        if not broker:
            results += [(node, False, "Python bindings for Broker: %s" % errmsg)]
            continue

        success, endpoint, sub = _send_event_init(node, event, args, result_event, topic)

        if success and result_event:
            sent += [(node, result_event, endpoint, sub)]
        else:
            sub.reset()
            endpoint.shutdown()
            results += [(node, success, "")]

    for (node, result_event, endpoint, sub) in sent:
        success, result_args = _send_event_wait(node, result_event, endpoint, sub)
        sub.reset()
        endpoint.shutdown()
        results += [(node, success, result_args)]

    return results

def _send_event_init(node, event, args, result_event, topic):

    host = node.addr
    endpoint = broker.Endpoint()
    subscriber = endpoint.make_subscriber(topic)

    with endpoint.make_status_subscriber(True) as status_subscriber:
        endpoint.peer(host, node.getPort(), 1)

        tries = 0

        while True:
            msgs = status_subscriber.get(1, 1)

            for msg in msgs:
                if isinstance(msg, broker.Status):
                    if msg.code() == broker.SC.PeerAdded:
                        ev = broker.zeek.Event(event, *args)
                        endpoint.publish(topic + "/" + repr(msg.context()), ev)
                        logging.debug("broker: %s(%s) to node %s", event,
                                      ", ".join(args), node.name)
                        return (True, endpoint, subscriber)

            tries += 1

            if tries > config.Config.commtimeout:
                return (False, "time-out", None)

def _send_event_wait(node, result_event, bc, sub):
    if not result_event:
        return (True, [])

    # Wait for reply event.
    tries = 0

    while True:
        msgs = sub.get(1, 1)

        for msg in msgs:
            (topic, event) = msg
            ev = broker.zeek.Event(event)
            args = ev.args()
            logging.debug("broker: %s(%s) from node %s", result_event,
                          ", ".join(args), node.name)
            return (True, args)

        tries += 1

        if tries > config.Config.commtimeout:
            logging.debug("broker: timeout during receive from node %s", node.name)
            return (False, "time-out")

