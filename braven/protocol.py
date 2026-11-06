from __future__ import annotations

import time
from pathlib import Path


def send_command(ser, cmd: str) -> None:
    ser.write((cmd.strip() + "\n").encode("utf-8"))
    ser.flush()


def stream_download_prefixed(
    ser,
    command: str,
    out_path: Path,
    *,
    expected_prefix: str,
    initial_timeout: float = 5.0,
    idle_timeout: float = 15.0,
) -> tuple[int, int]:
    """Send command, then write ONLY lines that start with expected_prefix.

    Stop when:
      - a non-matching line arrives after at least one matching line, or
      - no bytes arrive for idle_timeout after first data, or
      - initial_timeout elapses before first data.

    The output file is opened on the first matching line, so a download that
    captures nothing neither creates out_path nor truncates an existing one.

    Returns (lines_written, bytes_written).
    """
    try:
        ser.reset_input_buffer()
    except Exception:
        pass

    send_command(ser, command)

    buf = bytearray()
    wrote_lines = 0
    wrote_bytes = 0
    started = False
    t0 = time.monotonic()
    first_rx = None
    last_rx = t0

    f = None
    try:
        while True:
            n = ser.in_waiting
            chunk = ser.read(n if n else 4096)
            if chunk:
                if first_rx is None:
                    first_rx = time.monotonic()
                last_rx = time.monotonic()
                buf.extend(chunk)

                # drain complete lines
                while True:
                    try:
                        idx = buf.index(10)  # '\n'
                    except ValueError:
                        break
                    line_bytes = buf[:idx]
                    del buf[: idx + 1]
                    if line_bytes.endswith(b"\r"):
                        line_bytes = line_bytes[:-1]
                    try:
                        line = line_bytes.decode("utf-8", errors="replace")
                    except Exception:
                        line = line_bytes.decode("latin-1", errors="replace")

                    if line.startswith(expected_prefix):
                        if f is None:
                            out_path.parent.mkdir(parents=True, exist_ok=True)
                            f = open(out_path, "wb")
                        f.write(line_bytes + b"\n")
                        wrote_lines += 1
                        wrote_bytes += len(line_bytes) + 1
                        started = True
                    else:
                        if started:
                            return wrote_lines, wrote_bytes
                        # ignore preface noise until first matching line
                continue

            now = time.monotonic()
            if first_rx is None:
                if (now - t0) >= initial_timeout:
                    break
            else:
                if (now - last_rx) >= idle_timeout:
                    break
            time.sleep(0.005)
    finally:
        if f is not None:
            f.close()

    return wrote_lines, wrote_bytes
