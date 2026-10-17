"""Independent byte vectors from the manufacturer's Web App protocol."""

import pytest

from custom_components.volcano_integration.protocol import (
    ProtocolError,
    decode_status,
    decode_temperature,
    decode_text,
    decode_vibration,
    encode_temperature,
    encode_vibration,
)


@pytest.mark.parametrize(
    ("raw", "heat", "pump"),
    [
        ("0000", False, False),
        ("2300", True, False),
        ("0030", False, True),
        ("2330", True, True),
        ("2306", True, False),
        ("2336", True, True),
        ("2302", True, False),
        ("2326", True, True),
        ("e3c6", True, False),
    ],
)
def test_status_bits(raw, heat, pump):
    result = decode_status(bytes.fromhex(raw))
    assert (result.heat, result.pump, result.raw) == (heat, pump, raw)


def test_wire_widths_and_units():
    assert decode_temperature(bytes.fromhex("a406")) == 170
    assert encode_temperature(170) == bytes.fromhex("a4060000")
    assert encode_temperature(230) == bytes.fromhex("fc080000")
    assert decode_text(b"V1.2\x00\x00") == "V1.2"


def test_vibration_commands_do_not_replace_other_bits():
    assert encode_vibration(True) == bytes.fromhex("00040000")
    assert encode_vibration(False) == bytes.fromhex("00040100")
    assert decode_vibration(bytes.fromhex("fffb")) is True
    assert decode_vibration(bytes.fromhex("ffff")) is False


@pytest.mark.parametrize("data", [b"", b"\x23"])
def test_short_read_rejected(data):
    with pytest.raises(ProtocolError):
        decode_status(data)
    with pytest.raises(ProtocolError):
        decode_temperature(data)


@pytest.mark.parametrize("raw", ["ffff", "4bff"])
def test_invalid_temperature_cannot_satisfy_a_workflow(raw):
    with pytest.raises(ProtocolError):
        decode_temperature(bytes.fromhex(raw))


@pytest.mark.parametrize("value", [39, 39.9, 230.1, 231, float("nan"), float("inf")])
def test_bad_setpoint_rejected(value):
    with pytest.raises(ValueError):
        encode_temperature(value)


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(170.4, 170), (170.5, 171), (170.6, 171), ((350 - 32) * 5 / 9, 177), (40.1, 40), (229.9, 230)],
)
def test_setpoints_use_whole_degrees_in_tenths_wire_units(requested, expected):
    assert encode_temperature(requested) == (expected * 10).to_bytes(4, "little")
