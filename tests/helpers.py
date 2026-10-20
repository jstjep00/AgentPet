"""Test helpers: a temporary home for all of AgentPet's places, and a stand-in for the running pets
that collects what the hooks send."""

from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

from agentpet import places


class FakeHome:
    """Points every AgentPet folder (and ~) at a short temporary directory."""

    def __enter__(self):
        # short on purpose: a Unix socket path must stay under about 100 bytes (macOS)
        self.tmp = tempfile.TemporaryDirectory(dir="/tmp" if os.path.isdir("/tmp") and os.name != "nt" else None)
        d = os.path.realpath(self.tmp.name)       # macOS: /tmp is a link to /private/tmp
        self.env = mock.patch.dict(os.environ, {"HOME": d, "USERPROFILE": d, "LOCALAPPDATA": d,
                                                 "XDG_RUNTIME_DIR": d, "XDG_STATE_HOME": d, "XDG_CONFIG_HOME": d})
        self.env.start()
        return d

    def __exit__(self, *exc):
        self.env.stop()
        self.tmp.cleanup()


class Pets:
    """A stand-in for the running pets on a Unix socket: collects the lines sent to it."""

    def __init__(self):
        self.lines: list[bytes] = []
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(places.channel())
        self.sock.listen(8)
        self.sock.settimeout(5)
        self.got = threading.Event()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            data = b""
            with conn:
                while chunk := conn.recv(65536):
                    data += chunk
            self.lines.extend(data.splitlines())
            self.got.set()

    def wait(self, n: int, timeout: float = 3.0) -> list[bytes]:
        import time

        end = time.monotonic() + timeout
        while len(self.lines) < n and time.monotonic() < end:
            time.sleep(0.01)
        return self.lines

    def close(self):
        """Stops taking connections. (Closing alone does not wake a thread blocked in accept() on
        Linux, which would keep accepting; shutting the socket down does.)"""
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
        try:
            os.unlink(places.channel())
        except OSError:
            pass


posix_only = unittest.skipIf(sys.platform == "win32", "Unix sockets; Windows is covered by the Qt test")
