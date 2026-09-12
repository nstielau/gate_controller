"""MiniMQTT adapter: short idle polls, longer TLS and packet-read deadlines.

Uses the private socket hooks in the pinned MiniMQTT bundle (20260909).
Keep this adapter's regression tests when updating that dependency.
"""

from adafruit_minimqtt.adafruit_minimqtt import MQTT

POLL_SECONDS = 0.02
IDLE_SOCKET_SECONDS = 0.01
NETWORK_SECONDS = 5


class GateMQTT(MQTT):
    _polling = False

    def poll(self):
        # MiniMQTT checks timeout >= _socket_timeout before reading anything.
        self._socket_timeout = IDLE_SOCKET_SECONDS
        self._polling = True
        try:
            return self.loop(timeout=POLL_SECONDS)
        finally:
            self._polling = False
            self._socket_timeout = NETWORK_SECONDS
            if self._sock is not None:
                self._sock.settimeout(NETWORK_SECONDS)

    def _wait_for_msg(self, timeout=None):
        self._reading_header = True
        self.message_retained = False
        if self._polling:
            self._sock.settimeout(IDLE_SOCKET_SECONDS)
        try:
            return super()._wait_for_msg(timeout=timeout)
        finally:
            if self._polling and self._sock is not None:
                self._sock.settimeout(NETWORK_SECONDS)

    def _sock_exact_recv(self, bufsize, timeout=None):
        result = super()._sock_exact_recv(bufsize, timeout=timeout)
        if getattr(self, "_reading_header", False):
            self._reading_header = False
            self.message_retained = bool(result[0] & 1) if result else False
        if self._polling:
            # A first byte arrived. Allow fragmented packet contents time to arrive.
            self._sock.settimeout(NETWORK_SECONDS)
        return result

    def close(self):
        """Release a failed connection without waiting for network traffic."""
        self._close_socket()
        self._is_connected = False
        self._subscribed_topics = []
