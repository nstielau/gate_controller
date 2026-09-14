"""Small bounded HTTPS client for the fixed Firebase device API.

Supports Content-Length and chunked HTTP/1.1; no redirects, cookies, compression,
HTTP downgrade, or caller-selected hosts. Socket ownership always stays here.
"""

import json
import ssl
import time

HOST = "drawbridge-45487.firebaseapp.com"
PREFIX = "/device-api/v1/"
# Allowed device-ID characters, not a credential.
DEVICE_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789-"  # pragma: allowlist secret


class Response:
    def __init__(self, sock, limit, service, deadline):
        self.sock = sock
        self.limit = limit
        self.service = service
        self.deadline = deadline
        self.buffer = bytearray()
        self.total = 0
        self.header_bytes = 0
        line = self.line()
        parts = line.split(b" ")
        if len(parts) < 2 or parts[0] not in (b"HTTP/1.0", b"HTTP/1.1"):
            raise ValueError("invalid_http")
        self.status = int(parts[1])
        headers = {}
        while True:
            line = self.line()
            if not line:
                break
            key, separator, value = line.partition(b":")
            if not separator or key.lower() in headers:
                raise ValueError("invalid_headers")
            headers[key.lower()] = value.strip().lower()
        if headers.get(b"content-encoding", b"identity") != b"identity":
            raise ValueError("unsupported_encoding")
        self.chunked = headers.get(b"transfer-encoding") == b"chunked"
        if b"transfer-encoding" in headers and not self.chunked:
            raise ValueError("unsupported_transfer")
        if self.chunked and b"content-length" in headers:
            raise ValueError("ambiguous_length")
        self.length = int(headers.get(b"content-length", b"0"))
        if not 0 <= self.length <= limit:
            raise ValueError("response_too_large")
        if self.status != 204 and not self.chunked and b"content-length" not in headers:
            raise ValueError("missing_length")

    def receive(self):
        self.service()
        if time.monotonic() >= self.deadline:
            raise OSError("http_deadline")
        chunk = bytearray(512)
        count = self.sock.recv_into(chunk)
        if not count:
            raise OSError("short_response")
        self.buffer.extend(chunk[:count])

    def line(self):
        while b"\r\n" not in self.buffer:
            if len(self.buffer) > 4096:
                raise ValueError("headers_too_large")
            self.receive()
        index = self.buffer.index(b"\r\n")
        result = bytes(self.buffer[:index])
        del self.buffer[: index + 2]
        self.header_bytes += index + 2
        if self.header_bytes > 8192:
            raise ValueError("headers_too_large")
        return result

    def take(self, count):
        while not self.buffer:
            self.receive()
        count = min(count, len(self.buffer), 512)
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result

    def chunks(self):
        remaining = self.length
        while True:
            if self.chunked:
                remaining = int(self.line().split(b";", 1)[0], 16)
                if remaining == 0:
                    while self.line():
                        pass
                    return
            if remaining < 0 or self.total + remaining > self.limit:
                raise ValueError("response_too_large")
            while remaining:
                chunk = self.take(remaining)
                self.total += len(chunk)
                remaining -= len(chunk)
                yield chunk
            if not self.chunked:
                return
            if self.line() != b"":
                raise ValueError("invalid_chunk")

    def json(self):
        data = bytearray()
        for chunk in self.chunks():
            data.extend(chunk)
        return json.loads(data.decode("utf-8"))


class DeviceHTTP:
    def __init__(self, pool, device_id, token):
        if (
            len(token) != 64
            or any(c not in "0123456789abcdef" for c in token)
            or not device_id
            or len(device_id) > 64
            or any(c not in DEVICE_CHARS for c in device_id)
        ):
            raise ValueError("invalid_ota_identity")
        self.pool, self.device_id, self.token = pool, device_id, token

    def request(self, route, service, consume, limit=4096, body=None):
        if route not in ("manifest", "report") and not (
            route.startswith("artifact?sequence=") and route[18:].isdigit()
        ):
            raise ValueError("invalid_ota_route")
        raw = self.pool.socket(self.pool.AF_INET, self.pool.SOCK_STREAM)
        sock = None
        try:
            raw.settimeout(5)
            context = ssl.create_default_context()
            sock = context.wrap_socket(raw, server_hostname=HOST)
            sock.settimeout(5)
            service()
            sock.connect((HOST, 443))
            payload = json.dumps(body).encode() if body is not None else b""
            headers = (
                "{} {}{} HTTP/1.1\r\nHost: {}\r\nAuthorization: Bearer {}\r\n"
                "X-Device-ID: {}\r\nAccept-Encoding: identity\r\nConnection: close\r\n"
                "Content-Type: application/json\r\nContent-Length: {}\r\n\r\n"
            ).format(
                "POST" if body is not None else "GET",
                PREFIX,
                route,
                HOST,
                self.token,
                self.device_id,
                len(payload),
            ).encode() + payload
            deadline = time.monotonic() + 45
            sent = 0
            while sent < len(headers):
                service()
                if time.monotonic() >= deadline:
                    raise OSError("http_deadline")
                count = sock.send(headers[sent:])
                if not count:
                    raise OSError("short_send")
                sent += count
            response = Response(sock, limit, service, deadline)
            if response.status not in (200, 204):
                raise OSError("http_status_{}".format(response.status))
            return consume(response)
        finally:
            if sock is not None:
                sock.close()
            raw.close()
