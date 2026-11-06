"""The `braven` commands end to end, against a fake device on a pty."""

from __future__ import annotations

import json

from conftest import SUMMARY_LINES, needs_pty, run_cli
from fake_device import FakeDevice, lines

pytestmark = needs_pty

SIM_ARGS = [
    "0080",
    "010",
    "0000",
    "000",
    "07100",
    "0000",
    "000",
    "00002",
    "0",
    "1",
    "0",
    "1",
]


def test_summary_writes_parsed_json(tmp_path):
    def respond(cmd):
        return lines(*SUMMARY_LINES) if cmd == "summary" else None

    out = tmp_path / "summary.json"
    with FakeDevice(respond) as dev:
        result = run_cli(["summary", "--port", dev.port, "--out", str(out)], 20)
    assert result.returncode == 0, result.stderr
    assert dev.commands == ["summary"]
    parsed = json.loads(out.read_text())
    assert parsed["Rocket"] == "Adrian's BRav"
    assert parsed["pad_ASL"] == "6806"
    assert "SUMMARY" not in json.dumps(parsed)  # header line is skipped


def test_simulate_sends_fields_verbatim():
    with FakeDevice() as dev:
        result = run_cli(["simulate", "--port", dev.port, *SIM_ARGS], 20)
    assert result.returncode == 0, result.stderr
    # Fixed-width fields keep their leading zeros.
    assert dev.commands == ["start sim " + " ".join(SIM_ARGS)]


def test_simulate_rejects_out_of_range_drag_code():
    with FakeDevice() as dev:
        args = [*SIM_ARGS[:-1], "10"]
        result = run_cli(["simulate", "--port", dev.port, *args], 20)
    assert result.returncode == 2
    assert dev.commands == []


def test_configure_takes_profile_as_positional_argument():
    with FakeDevice() as dev:
        result = run_cli(["configure", "--port", dev.port, "2nd stage"], 20)
    assert result.returncode == 0, result.stderr
    assert dev.commands == ["2nd stage"]
