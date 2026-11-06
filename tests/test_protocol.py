"""stream_download_prefixed against a fake device on a pseudo-terminal."""

from __future__ import annotations

import time

from conftest import needs_pty
from fake_device import FakeDevice, lines

from braven.protocol import send_command, stream_download_prefixed
from braven.serialio import open_port

pytestmark = needs_pty

LOW = [
    "@ LOG_LOW 120 2023-02-14 11:23:31 sync 10 CRC: 0001",
    "@ LOG_LOW 120 2023-02-14 11:23:31 sync 30 CRC: 0002",
    "@ LOG_LOW 120 2023-02-14 11:23:31 sync 50 CRC: 0003",
]


def _download(dev, out, *, initial=1.0, idle=0.5):
    ser = open_port(dev.port, timeout=0.1)
    try:
        t0 = time.monotonic()
        result = stream_download_prefixed(
            ser,
            "download l",
            out,
            expected_prefix="@ LOG_LOW",
            initial_timeout=initial,
            idle_timeout=idle,
        )
        return result, time.monotonic() - t0
    finally:
        ser.close()


def test_send_command_writes_one_newline_terminated_line():
    with FakeDevice() as dev:
        ser = open_port(dev.port, timeout=0.1)
        try:
            send_command(ser, "  summary \n")
        finally:
            ser.close()
        time.sleep(0.2)
    assert bytes(dev.received) == b"summary\n"


def test_download_keeps_only_prefixed_lines_and_stops_on_prefix_change(tmp_path):
    def respond(cmd):
        if cmd == "download l":
            # Preface noise, the log, then a different line that ends it,
            # then more data that must not be captured.
            return lines("@ BLR_STAT noise", *LOW, "@ BLR_STAT after", LOW[0])
        return None

    out = tmp_path / "low.txt"
    with FakeDevice(respond) as dev:
        (n_lines, n_bytes), elapsed = _download(dev, out, idle=5.0)
    assert dev.commands == ["download l"]
    assert n_lines == 3
    assert out.read_bytes() == "".join(f"{x}\n" for x in LOW).encode()
    assert n_bytes == len(out.read_bytes())
    # The prefix change, not the 5 s idle timeout, ended the download.
    assert elapsed < 3.0


def test_download_stops_after_idle_timeout(tmp_path):
    def respond(cmd):
        return lines(*LOW) if cmd == "download l" else None

    out = tmp_path / "low.txt"
    with FakeDevice(respond) as dev:
        (n_lines, _), elapsed = _download(dev, out, idle=0.5)
    assert n_lines == 3
    assert 0.5 <= elapsed < 3.0


def test_download_gives_up_after_initial_timeout_on_silent_device(tmp_path):
    out = tmp_path / "low.txt"
    with FakeDevice() as dev:
        (n_lines, n_bytes), elapsed = _download(dev, out, initial=0.5, idle=10.0)
    assert (n_lines, n_bytes) == (0, 0)
    assert 0.5 <= elapsed < 3.0
    assert not out.exists()
