import asyncio
import json
import logging

from ZeekControl import config, version

errmsg = ""

try:
    import broker
    import broker.zeek
except ImportError as e:
    broker = None
    errmsg = e


def version_tuple(s):
    """
    Return a tuple of the first two parts of a version. E.g. "10.4.1" -> (10,4)
    """
    parts = []
    for v in s.split(".")[:2]:
        try:
            v = int(v)
        except ValueError:
            v = 0
        parts += [v]
    return tuple(parts)


try:
    websockets_errmsg = None
    import websockets
    import websockets.exceptions as websockets_exceptions

    # Tested with 10.4 on Ubuntu 24.04
    websockets_version = version_tuple(websockets.__version__)
    if websockets_version < (10, 4):
        websockets_errmsg = f"Need websockets package version 10.4 or later, have {websockets.__version__}"

except ImportError as e:
    websockets = None
    websockets_exceptions = None
    websockets_version = (0, 0)
    websockets_errmsg = f"Failed to import websockets module ({e!r})"

# Communication with running nodes.


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
    clusterbackend = config.Config.clusterbackend
    if config.Config.usewebsocket:
        return asyncio.run(ws_send_events(events, topic))
    elif clusterbackend.lower() == "broker":
        return broker_send_events_parallel(events, topic)

    # Error if non-Broker backend in selected and UseWebSocket is not set.
    results = []
    for node, _, _, _ in events:
        results += [
            (
                node,
                False,
                f"command execution with cluster backend '{clusterbackend}' requires UseWebSocket = 1",
            )
        ]
    return results


def broker_send_events_parallel(events, topic):
    results = []
    sent = []

    for node, event, args, result_event in events:
        if not broker:
            results += [(node, False, f"Python bindings for Broker: {errmsg}")]
            continue

        success, endpoint, sub = _send_event_init(
            node, event, args, result_event, topic
        )

        if success and result_event:
            sent += [(node, result_event, endpoint, sub)]
        else:
            sub.reset()
            endpoint.shutdown()
            results += [(node, success, "")]

    for node, result_event, endpoint, sub in sent:
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
                        logging.debug(
                            "broker: %s(%s) to node %s",
                            event,
                            ", ".join(args),
                            node.name,
                        )
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
            logging.debug(
                "broker: %s(%s) from node %s", result_event, ", ".join(args), node.name
            )
            return (True, args)

        tries += 1

        if tries > config.Config.commtimeout:
            logging.debug("broker: timeout during receive from node %s", node.name)
            return (False, "time-out")


class WebSocketError(Exception):
    pass


class WebSocketClient:
    """
    Small wrapper around the websockets library to send
    and receive simple Zeek events via v1/messages/json.

    This is good enough for Zeekctl. If you have a use for
    this, put it in a library :-)
    """

    DEFAULT_TIMEOUT = 10.0

    def __init__(self, uri, *, application_name=None, timeout=DEFAULT_TIMEOUT):
        self.__uri = uri
        self.__application_name = application_name
        self.__timeout = timeout

        self.__c = None

    async def __aenter__(self):
        kwargs = {}
        if self.__application_name:
            headers = {"X-Application-Name": self.__application_name}
            # websockets version 10.4 used extra_headers as kwarg and
            # only in 14.0 started using additional_headers. Meh.
            if websockets_version < (14, 0):
                kwargs = {"extra_headers": headers}
            else:
                kwargs = {"additional_headers": headers}

        self.__c = await websockets.connect(
            uri=self.__uri,
            open_timeout=self.__timeout,
            close_timeout=self.__timeout,
            **kwargs,
        )

        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.__c.close()

    async def send_json(self, data):
        try:
            await self.__c.send(json.dumps(data))
        except (
            websockets_exceptions.ConnectionClosed,
            websockets_exceptions.ConnectionClosedError,
        ) as e:
            raise WebSocketError(e)

    async def recv_json(self):
        try:
            return json.loads(await asyncio.wait_for(self.__c.recv(), self.__timeout))
        except (
            asyncio.TimeoutError,
            websockets_exceptions.ConnectionClosed,
            websockets_exceptions.ConnectionClosedError,
        ) as e:
            raise WebSocketError(e)

    async def v1_hello(self, subscriptions):
        """
        Send the initial subscription array for v1/messages/json.
        """
        await self.send_json(subscriptions)
        ack = await self.recv_json()
        if ack.get("type") != "ack":
            raise WebSocketError(f"Unexpected ack type {ack!r}")
        return ack

    async def v1_event(self, topic, name, args=None):
        """
        Send an event in v1/messages/json format.
        """
        ev_args = [self.v1_arg(a) for a in (args or [])]
        d = {
            "type": "data-message",
            "topic": topic,
            "@data-type": "vector",
            "data": [
                {"@data-type": "count", "data": 1},  # Format
                {"@data-type": "count", "data": 1},  # Type
                {
                    "@data-type": "vector",
                    "data": [  # Event vector
                        {"@data-type": "string", "data": name},
                        {"@data-type": "vector", "data": ev_args},
                    ],
                },
            ],
        }

        return await self.send_json(d)

    async def v1_recv_event(self):
        """
        Wait for a JSON message and interpret it as v1/messages/json event.

        Returns a (topic, name, args) tuple.
        """
        d = await self.recv_json()
        if d["type"] != "data-message":
            raise WebSocketError(f"unexpected event reply {d!r}")

        # See event_v1() for the format.
        ev_name = d["data"][2]["data"][0]["data"]
        ev_args = d["data"][2]["data"][1]["data"]
        ev_args_vals = [ev_arg["data"] for ev_arg in ev_args]
        return d["topic"], ev_name, ev_args_vals

    @staticmethod
    def v1_arg(arg):
        data_type = None
        data = None

        if isinstance(arg, int):
            data_type = "count"
            data = arg
        elif isinstance(arg, str):
            data_type = "string"
            data = arg
        else:
            raise TypeError(f"Unsupported arg {arg!r} of type {type(arg)}")

        return {
            "@data-type": data_type,
            "data": data,
        }


async def ws_send_events(events, topic):
    """
    Use a short-lived WebSocket connection to the manager and send
    events serially to individual node topics and await the response.

    This will not work correctly if two zeekctl processes do this at
    the same time. If we want this, we'd need to make the topic unique
    and pass it as event parameter so the control scripts can use it
    for their reply. Punt on that for now, I think the same issue
    exists with the native Broker integration, too.
    """
    results = []

    if websockets_errmsg:
        for node, event, args, result_event in events:
            results += [(node, False, websockets_errmsg)]
        return results

    if config.Config.websocketurl:
        url = config.Config.websocketurl
    else:
        host = config.Config.websockethost
        port = config.Config.websocketport
        url = f"ws://{host}:{port}/v1/messages/json"

    timeout = config.Config.websockettimeout

    # Include X-Application-Name as HTTP header so it shows up in cluster.log
    application_name = f"zeekctl/{version.VERSION}/{websockets.__version__}"

    try:
        async with WebSocketClient(
            url, application_name=application_name, timeout=timeout
        ) as ws:
            await ws.v1_hello([topic])

            for node, event, args, result_event in events:
                # Use the topic separator configured by the backend for publishing
                # to individual node topics.
                topic_sep = config.Config.clustertopicseparator
                topic = topic_sep.join(["zeek", "cluster", "node", node.name, ""])

                try:
                    await ws.v1_event(topic, event, args)
                    rtopic, rname, rargs = await ws.v1_recv_event()
                except WebSocketError as e:
                    results += [(node, False, repr(e))]
                    continue
                else:
                    # Did we even receive the right event?
                    if result_event != rname:
                        results += [
                            (node, False, f"expected '{result_event}' got '{rname}'")
                        ]
                        continue

                    # Figure out which node sent the reply. It's the last part
                    # in the reply topic. The / is hard-coded in the control
                    # scripts, so we try that first if it's found, else fallback
                    # to topic_sep (e.g, could be "." for ZeroMQ, NATS or RabbitMQ)
                    if "/" in rtopic:
                        rnode = rtopic.rsplit("/", 1)[-1]
                    else:
                        rnode = rtopic.rsplit(topic_sep, 1)[-1]

                    # Expect a reply from the addressed node, or an empty node if
                    # this a standalone setup.
                    if rnode != node.name and not (
                        config.Config.standalone and rnode == ""
                    ):
                        results += [
                            (
                                node,
                                False,
                                f"'unexpected {rnode}' in '{topic}', expected '{node.name}'",
                            )
                        ]
                        continue

                    results += [(node, True, rargs)]

    except (ConnectionRefusedError, asyncio.TimeoutError, WebSocketError) as e:
        for node, event, args, result_event in events:
            results += [(node, False, str(e))]

    return results
