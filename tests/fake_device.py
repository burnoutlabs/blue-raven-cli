"""A fake Blue Raven on a pseudo-terminal, for tests that need a serial port.

The CLI opens the slave side by path, exactly as it would open COM7 or
/dev/ttyACM0. A background thread on the master side records every byte the
CLI sends and, for each complete command line, writes back whatever the
responder returns. A responder that returns nothing is a device that never
answers.

POSIX only: ``os.openpty`` does not exist on Windows.
"""

from __future__ import annotations

import os
import select
import threading
import time
import tty
from typing import Callable, Iterable, List, Optional, Union

# A reply is raw bytes, or a sequence of (delay_seconds, bytes) chunks sent in
# order, so a test can model a device that pauses mid-stream.
Reply = Union[bytes, Iterable["tuple[float, bytes]"]]
Responder = Callable[[str], Optional[Reply]]


def silent(_command: str) -> None:
    """A device that receives commands and never answers."""
    return None


def lines(*text: str) -> bytes:
    """Encode lines the way the device sends them (CRLF-terminated)."""
    return b"".join(t.encode("utf-8") + b"\r\n" for t in text)


class FakeDevice:
    def __init__(self, responder: Responder = silent) -> None:
        self.responder = responder
        self.received = bytearray()
        self.commands: List[str] = []
        self._master, self._slave = os.openpty()
        # No echo and no newline translation on the slave, so the bytes the
        # CLI writes reach the master unchanged.
        tty.setraw(self._slave)
        self.port = os.ttyname(self._slave)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> "FakeDevice":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        for fd in (self._master, self._slave):
            try:
                os.close(fd)
            except OSError:
                pass

    def _send(self, reply: Reply) -> None:
        chunks = [(0.0, reply)] if isinstance(reply, bytes) else reply
        for delay, data in chunks:
            if delay:
                time.sleep(delay)
            os.write(self._master, data)

    def _run(self) -> None:
        pending = bytearray()
        while True:
            ready, _, _ = select.select([self._master], [], [], 0.05)
            if not ready:
                # Stop only once nothing is pending, so a command the CLI
                # wrote just before exiting is still recorded.
                if self._stop.is_set():
                    return
                continue
            try:
                data = os.read(self._master, 4096)
            except OSError:
                return
            self.received.extend(data)
            pending.extend(data)
            while b"\n" in pending:
                idx = pending.index(b"\n")
                command = pending[:idx].decode("utf-8", "replace").strip()
                del pending[: idx + 1]
                self.commands.append(command)
                reply = self.responder(command)
                if reply:
                    self._send(reply)
