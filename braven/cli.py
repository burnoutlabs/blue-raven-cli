"""
Blue Raven CLI
===============

CLI for Featherweight Blue Raven over USB. Supports port discovery, live status,
flight summaries and logs, canned profiles, naming, beeps/LEDs, erase,
calibration, and simulator control.

Power the device before USB connection. Disconnect energetics during tests.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

import typer

from .files import write_text
from .parsers import parse_summary_block
from .protocol import send_command, stream_download_prefixed
from .serialio import list_serial_ports, open_port

app = typer.Typer(
    add_completion=False, help="Operate the Featherweight Blue Raven over USB."
)


def _ensure_output_path(path_str: str) -> Path:
    p = Path(path_str).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@app.command(help="List available serial ports.")
def ports(
    json_out: bool = typer.Option(
        False, "--json", help="Output as JSON instead of tab-separated text."
    ),
) -> None:
    port_infos = list_serial_ports()
    if json_out:
        items = []
        for p in port_infos:
            items.append(
                {
                    "device": p.device,
                    "name": getattr(p, "name", None),
                    "description": getattr(p, "description", None),
                    "hwid": getattr(p, "hwid", None),
                }
            )
        typer.echo(json.dumps(items, indent=2))
    else:
        for p in port_infos:
            desc = getattr(p, "description", "") or ""
            typer.echo(f"{p.device}\t{desc}")


@app.command(help="Stream live status lines for a given duration.")
def status(
    port: str = typer.Option(
        ..., help="Serial port to open (e.g. COM5 or /dev/ttyACM0)."
    ),
    duration: float = typer.Option(
        5.0, min=0.1, help="Number of seconds to stream status lines."
    ),
    out: Optional[str] = typer.Option(
        None, help="Optional file to save the captured status lines."
    ),
) -> None:
    try:
        ser = open_port(port, timeout=0.2)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(code=1)
    out_lines: List[str] = []
    deadline = time.time() + duration
    try:
        while time.time() < deadline:
            raw = ser.readline()
            if raw:
                try:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    line = raw.decode("latin-1", errors="replace").rstrip()
                typer.echo(line)
                out_lines.append(line)
            else:
                time.sleep(0.01)
    finally:
        ser.close()
    if out:
        p = _ensure_output_path(out)
        write_text(p, "\n".join(out_lines) + "\n")
        typer.echo(f"Captured {len(out_lines)} status lines to {p}")


@app.command(help="Retrieve the last flight summary and write it to a JSON file.")
def summary(
    port: str = typer.Option(..., help="Serial port to open."),
    out: str = typer.Option(..., help="Path to write the JSON summary output."),
) -> None:
    try:
        ser = open_port(port, timeout=1.0)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(code=1)
    try:
        ser.reset_input_buffer()
        send_command(ser, "summary")
        lines = []
        saw_crc = False
        last_rx = time.time()
        while True:
            raw = ser.readline()
            if raw:
                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    line = raw.decode("latin-1", errors="replace").strip()
                lines.append(line)
                last_rx = time.time()
                if "CRC" in line.upper():
                    saw_crc = True
            else:
                if saw_crc and (time.time() - last_rx) > 1.0:
                    break
                time.sleep(0.05)
            if len(lines) > 1000 and not saw_crc:
                break
        parsed = parse_summary_block(lines[1:]) if len(lines) > 1 else {}
        p = _ensure_output_path(out)
        write_text(p, json.dumps(parsed, indent=2))
        typer.echo(f"Wrote summary with {len(parsed)} fields to {p}")
    finally:
        ser.close()


@app.command(name="download-low", help="Download low-rate (50 Hz) log to a file.")
def download_low(
    port: str = typer.Option(..., help="Serial port to open."),
    out: str = typer.Option(..., help="File path to write the raw low-rate log."),
    initial: float = typer.Option(5.0, help="Seconds to wait for first byte."),
    idle: float = typer.Option(8.0, help="Idle seconds after last byte to stop."),
) -> None:
    try:
        ser = open_port(port, timeout=0.1)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(1)
    try:
        lines, bytes_ = stream_download_prefixed(
            ser,
            "download l",
            Path(out),
            expected_prefix="@ LOG_LOW",
            initial_timeout=initial,
            idle_timeout=idle,
        )
        typer.echo(f"Wrote {lines} lines ({bytes_} bytes) to {out}")
    finally:
        ser.close()


@app.command(name="download-high", help="Download high-rate (500 Hz) log to a file.")
def download_high(
    port: str = typer.Option(..., help="Serial port to open."),
    out: str = typer.Option(..., help="File path to write the raw high-rate log."),
    initial: float = typer.Option(8.0, help="Seconds to wait for first byte."),
    idle: float = typer.Option(20.0, help="Idle seconds after last byte to stop."),
) -> None:
    try:
        ser = open_port(port, timeout=0.1)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(1)
    try:
        lines, bytes_ = stream_download_prefixed(
            ser,
            "download h",
            Path(out),
            expected_prefix="@ LOG_HIR",
            initial_timeout=initial,
            idle_timeout=idle,
        )
        typer.echo(f"Wrote {lines} lines ({bytes_} bytes) to {out}")
    finally:
        ser.close()


@app.command(help="Load a pre-defined deployment profile.")
def configure(
    port: str = typer.Option(..., help="Serial port to open."),
    profile: str = typer.Argument(
        ..., help="Deployment profile: default|sustainer|2nd stage|3 stage sim"
    ),
) -> None:
    valid = {"default", "sustainer", "2nd stage", "3 stage sim"}
    if profile not in valid:
        typer.echo(
            f"Unknown profile '{profile}'. Expected one of: {', '.join(valid)}",
            err=True,
        )
        raise typer.Exit(code=1)
    try:
        ser = open_port(port, timeout=1.0)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(code=1)
    try:
        send_command(ser, profile)
        typer.echo(f"Sent profile '{profile}'")
    finally:
        ser.close()


@app.command(help="Set the rocket name (up to 13 characters).")
def name(
    port: str = typer.Option(..., help="Serial port to open."),
    name: str = typer.Argument(..., help="Name to set (≤13 characters)."),
) -> None:
    if len(name) > 13:
        typer.echo("Name must be 13 characters or fewer", err=True)
        raise typer.Exit(code=1)
    try:
        ser = open_port(port, timeout=1.0)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(code=1)
    try:
        send_command(ser, f"set name {name}")
        typer.echo(f"Set name to '{name}'")
    finally:
        ser.close()


@app.command(help="Change the operating mode.")
def mode(
    port: str = typer.Option(..., help="Serial port to open."),
    mode: str = typer.Argument(..., help="Mode: checkout|prelaunch"),
) -> None:
    valid_modes = {"checkout", "prelaunch"}
    if mode not in valid_modes:
        typer.echo(
            f"Invalid mode '{mode}'. Expected 'checkout' or 'prelaunch'", err=True
        )
        raise typer.Exit(code=1)
    try:
        ser = open_port(port, timeout=1.0)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(code=1)
    try:
        send_command(ser, mode)
        typer.echo(f"Sent mode '{mode}'")
    finally:
        ser.close()


@app.command(help="Enable or disable the automatic beeper.")
def beeps(
    port: str = typer.Option(..., help="Serial port to open."),
    state: str = typer.Argument(..., help="on|off"),
) -> None:
    if state not in {"on", "off"}:
        typer.echo("State must be 'on' or 'off'", err=True)
        raise typer.Exit(code=1)
    try:
        ser = open_port(port, timeout=1.0)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(code=1)
    try:
        send_command(ser, f"beeps {state}")
        typer.echo(f"Beeper turned {state}")
    finally:
        ser.close()


@app.command(help="Manually control the LED colour or hold state.")
def leds(
    port: str = typer.Option(..., help="Serial port to open."),
    c: int = typer.Argument(
        ..., min=0, max=3, help="Colour code: 0=red,1=green,2=blue,3=manual"
    ),
    s: int = typer.Argument(..., min=0, max=1, help="State: 1=on/hold, 0=off/release"),
) -> None:
    try:
        ser = open_port(port, timeout=1.0)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(code=1)
    try:
        send_command(ser, f"LED {c} {s}")
        typer.echo(f"Sent LED command: colour {c}, state {s}")
    finally:
        ser.close()


@app.command(help="Erase flight data or configuration.")
def erase(
    port: str = typer.Option(..., help="Serial port to open."),
    target: str = typer.Argument(..., help="Target to erase: data|config"),
) -> None:
    if target not in {"data", "config"}:
        typer.echo("Target must be 'data' or 'config'", err=True)
        raise typer.Exit(code=1)
    try:
        ser = open_port(port, timeout=1.0)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(code=1)
    try:
        send_command(ser, f"erase {target}")
        typer.echo(f"Sent erase {target}")
    finally:
        ser.close()


@app.command(help="Accelerometer calibration helper.")
def calibrate(
    port: str = typer.Option(..., help="Serial port to open."),
    action: str = typer.Argument(..., help="Calibration action: start|axis|stop"),
) -> None:
    if action not in {"start", "axis", "stop"}:
        typer.echo("Action must be one of: start, axis, stop", err=True)
        raise typer.Exit(code=1)
    try:
        ser = open_port(port, timeout=1.0)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(code=1)
    try:
        send_command(ser, f"cal {action}")
        typer.echo(f"Sent calibration action '{action}'")
    finally:
        ser.close()


@app.command(help="Start the flight simulator with provided parameters.")
def simulate(
    port: str = typer.Option(..., help="Serial port to open."),
    a1: str = typer.Argument(..., help="Stage 1 thrust acceleration (g×10) or 0000"),
    t1: str = typer.Argument(..., help="Stage 1 burn duration (s×10) or 000"),
    a2: str = typer.Argument(..., help="Stage 2 thrust acceleration (g×10) or 0000"),
    t2: str = typer.Argument(..., help="Stage 2 burn duration (s×10) or 000"),
    a3: str = typer.Argument(..., help="Stage 3 thrust acceleration (g×10) or 0000"),
    t3: str = typer.Argument(..., help="Stage 3 burn duration (s×10) or 000"),
    astart2_alt: str = typer.Argument(
        ..., help="Fixed airstart altitude for stage 2 (ft AGL) or 0000"
    ),
    astart3_alt: str = typer.Argument(
        ..., help="Fixed airstart altitude for stage 3 (ft AGL) or 0000"
    ),
    drag_code_apo: int = typer.Argument(
        ..., min=0, max=9, help="Drag code for apogee output"
    ),
    drag_code_main: int = typer.Argument(
        ..., min=0, max=9, help="Drag code for main output"
    ),
    drag_code_3rd: int = typer.Argument(
        ..., min=0, max=9, help="Drag code for 3rd output"
    ),
    drag_code_4th: int = typer.Argument(
        ..., min=0, max=9, help="Drag code for 4th output"
    ),
) -> None:
    cmd_parts = [
        "start sim",
        a1,
        t1,
        a2,
        t2,
        a3,
        t3,
        astart2_alt,
        astart3_alt,
        str(drag_code_apo),
        str(drag_code_main),
        str(drag_code_3rd),
        str(drag_code_4th),
    ]
    cmd = " ".join(cmd_parts)
    try:
        ser = open_port(port, timeout=1.0)
    except Exception as exc:
        typer.echo(f"Failed to open {port}: {exc}", err=True)
        raise typer.Exit(code=1)
    try:
        send_command(ser, cmd)
        typer.echo(f"Sent simulator command: {cmd}")
    finally:
        ser.close()


if __name__ == "__main__":
    app()
