import time
from threading import Thread
from typing import Callable

from .frame import Frame
import websocket
import logging


# https://stomp.github.io/stomp-specification-1.1.html#Overview
VERSIONS = '1.0,1.1'


class Client:

    def __init__(self, url: str, on_close: Callable):
        self.url = url
        self.ws = websocket.WebSocketApp(self.url)
        self.ws.on_open = self._on_open
        self.ws.on_message = self._on_message
        self.ws.on_error = self._on_error
        self.ws.on_close = self._on_close

        self.on_close = on_close

        self.opened = False

        self.connected = False

        self.counter = 0
        self.subscriptions = {}

        self._connectCallback = None
        self.errorCallback = None

    def _connect(self, timeout=0):
        thread = Thread(target=self.ws.run_forever, kwargs={'ping_interval': 1})
        thread.daemon = True
        thread.start()

        total_ms = 0
        while self.opened is False:
            time.sleep(.25)
            total_ms += 250
            if 0 < timeout*1000 < total_ms:
                raise TimeoutError(f"Connection to {self.url} timed out")

    def _on_open(self, ws_app, *args):
        self.opened = True

    def _on_close(self, ws_app, *args):
        self.connected = False
        logging.error("Lost connection to " + self.ws.url)
        self._clean_up()
        self.on_close()

    def _on_error(self, ws_app, error, *args):
        logging.error({'msg': 'Websocket error.', 'error': error})

    def _on_message(self, ws_app, message, *args):
        logging.debug("\n<<< " + str(message))
        frame = Frame.unmarshall_single(message)

        if frame is None:
            return

        _results = []
        if frame.command == "CONNECTED":
            self.connected = True
            logging.debug("connected to server " + self.url)
            if self._connectCallback is not None:
                _results.append(self._connectCallback(frame))
        elif frame.command == "MESSAGE":

            subscription = frame.headers['subscription']

            if subscription in self.subscriptions:
                on_receive = self.subscriptions[subscription]
                message_id = frame.headers['message-id']

                def ack(headers):
                    if headers is None:
                        headers = {}
                    return self.ack(message_id, subscription, headers)

                def nack(headers):
                    if headers is None:
                        headers = {}
                    return self.nack(message_id, subscription, headers)

                frame.ack = ack
                frame.nack = nack

                _results.append(on_receive(frame))
            else:
                info = "Unhandled received MESSAGE: " + str(frame)
                logging.debug(info)
                _results.append(info)
        elif frame.command == 'RECEIPT':
            pass
        elif frame.command == 'ERROR':
            if self.errorCallback is not None:
                _results.append(self.errorCallback(frame))
        else:
            info = "Unhandled received MESSAGE: " + frame.command
            logging.error(info)
            _results.append(info)

        return _results

    def _transmit(self, command, headers, body=None):
        out = Frame.marshall(command, headers, body)
        logging.debug("\n>>> " + out)
        self.ws.send(out)

    def connect(
        self,
        login=None,
        passcode=None,
        host='/',
        headers=None,
        connect_callback=None,
        error_callback=None,
        timeout=0,
    ):

        logging.debug("Opening web socket...")
        self._connect(timeout)

        headers = headers if headers is not None else {}
        headers['host'] = host
        headers['accept-version'] = VERSIONS
        headers['heart-beat'] = '10000,10000'

        if login is not None:
            headers['login'] = login
        if passcode is not None:
            headers['passcode'] = passcode

        self._connectCallback = connect_callback
        self.errorCallback = error_callback

        self._transmit('CONNECT', headers)

    def disconnect(self, disconnect_callback=None, headers=None):
        if headers is None:
            headers = {}

        self._transmit("DISCONNECT", headers)
        self.ws.on_close = None
        self.ws.close()
        self._clean_up()

        if disconnect_callback is not None:
            disconnect_callback()

    def _clean_up(self):
        self.connected = False

    def send(self, destination, headers=None, body=None):
        if headers is None:
            headers = {}
        if body is None:
            body = ''
        headers['destination'] = destination
        return self._transmit("SEND", headers, body)

    def subscribe(self, destination, callback=None, headers=None):
        if headers is None:
            headers = {}

        if 'id' not in headers:
            headers['id'] = 'sub-' + str(self.counter)
            self.counter += 1

        if 'ack' not in headers:
            headers['ack'] = 'auto'

        headers['destination'] = destination
        self.subscriptions[headers["id"]] = callback
        self._transmit("SUBSCRIBE", headers)

        def unsubscribe():
            self.unsubscribe(headers["id"])

        return headers["id"], unsubscribe

    def unsubscribe(self, channel_id):
        del self.subscriptions[channel_id]
        return self._transmit("UNSUBSCRIBE", {
            "id": channel_id
        })

    def ack(self, message_id, subscription, headers):
        if headers is None:
            headers = {}
        headers["message-id"] = message_id
        headers['subscription'] = subscription
        return self._transmit("ACK", headers)

    def nack(self, message_id, subscription, headers):
        if headers is None:
            headers = {}
        headers["message-id"] = message_id
        headers['subscription'] = subscription
        return self._transmit("NACK", headers)
