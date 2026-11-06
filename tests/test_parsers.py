from conftest import SUMMARY_LINES

from braven.parsers import parse_summary_block


def test_summary_block_splits_on_first_colon():
    parsed = parse_summary_block(SUMMARY_LINES[1:])
    assert parsed["Rocket"] == "Adrian's BRav"
    # Times contain colons; only the first one separates key from value.
    assert parsed["Build"] == "02/14/2023 11:19:58000"
    assert parsed["landing time"] == "11:24:14680"
    assert parsed["pad_ASL"] == "6806"


def test_summary_block_ignores_lines_without_colon():
    assert parse_summary_block(["no separator here", "", "a: 1"]) == {"a": "1"}


def test_summary_block_last_line_keeps_trailing_fields_in_value():
    parsed = parse_summary_block(["max alt: 897 max vel: 228 CRC: 6FA7"])
    assert parsed == {"max alt": "897 max vel: 228 CRC: 6FA7"}
