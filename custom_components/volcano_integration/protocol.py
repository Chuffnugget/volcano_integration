"""Volcano wire format. Keep hardware assumptions separate from Home Assistant."""

import math
from dataclasses import dataclass

from .const import (
    FAHRENHEIT_ENABLED_MASK,
    HEATER_ENABLED_MASK,
    MAX_BRIGHTNESS,
    MAX_TEMP,
    MIN_BRIGHTNESS,
    MIN_TEMP,
    PUMP_ENABLED_MASK,
    VIBRATION_BIT_MASK,
)


class ProtocolError(ValueError):
    """A characteristic contains incomplete or invalid data."""


def decode_uint(data: bytes | bytearray, size: int = 2) -> int:
    """Decode a little-endian register without silently accepting short reads."""
    if len(data) < size:
        raise ProtocolError(f"Expected at least {size} bytes, received {len(data)}")
    return int.from_bytes(data[:size], "little")


def decode_temperature(data: bytes | bytearray) -> float:
    """Temperatures are unsigned tenths of a degree Celsius."""
    value = decode_uint(data) / 10
    # The official app rejects Math.round(value) >= 6536.
    if value >= 6535.5:
        raise ProtocolError("Device reported an invalid temperature sentinel")
    return value


def decode_brightness(data: bytes | bytearray) -> int:
    """Brightness is a uint16 percentage, not a single-byte register."""
    value = decode_uint(data)
    if not MIN_BRIGHTNESS <= value <= MAX_BRIGHTNESS:
        raise ProtocolError("Device reported invalid brightness")
    return value


def normalize_setpoint(value: float, unit: str = "C") -> int:
    """Validate and round to a whole degree in the requested display unit."""
    if unit not in {"C", "F"}:
        raise ValueError("Temperature unit must be C or F")
    minimum, maximum = (MIN_TEMP, MAX_TEMP) if unit == "C" else (104, 446)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"Temperature must be between {minimum} and {maximum} °{unit}")
    return math.floor(value + 0.5)


def encode_temperature(value: float, unit: str = "C") -> bytes:
    """Send a whole displayed degree as the nearest wire tenth of Celsius."""
    # The official app writes a 32-bit setpoint, but reads a 16-bit value.
    whole = normalize_setpoint(value, unit)
    celsius = whole if unit == "C" else (whole - 32) * 5 / 9
    return math.floor(celsius * 10 + 0.5).to_bytes(4, "little")


def decode_temperature_unit(data: bytes | bytearray) -> str:
    """Register 2 bit 9 selects Fahrenheit in S&B's Web App v3.4.1."""
    return "F" if decode_uint(data) & FAHRENHEIT_ENABLED_MASK else "C"


def encode_temperature_unit(unit: str) -> bytes:
    """Change only the Fahrenheit bit, preserving other register settings."""
    if unit not in {"C", "F"}:
        raise ValueError("Temperature unit must be C or F")
    return (FAHRENHEIT_ENABLED_MASK | (0x10000 if unit == "F" else 0)).to_bytes(4, "little")


def decode_text(data: bytes | bytearray) -> str:
    """Firmware strings can be NUL terminated."""
    try:
        return data.decode("utf-8").strip("\x00 \r\n")
    except UnicodeDecodeError as err:
        raise ProtocolError("Invalid UTF-8 device information") from err


@dataclass(frozen=True)
class Status:
    """Confirmed states and the raw register for diagnosing unknown firmware."""

    heat: bool | None
    pump: bool | None
    raw: str


def decode_status(data: bytes | bytearray) -> Status:
    """Decode register 1 flags as used by S&B's official Web App v3.4.1.

    Unrelated bits must not affect heater or pump state. Keep the entire
    payload as a diagnostic so firmware-specific flags remain inspectable.
    """
    value = decode_uint(data)
    return Status(bool(value & HEATER_ENABLED_MASK), bool(value & PUMP_ENABLED_MASK), data.hex())


def encode_vibration(enabled: bool) -> bytes:
    """Register writes are bit commands, not replacement register values.

    Bit 10 means vibration *disabled*. A 32-bit command contains the mask
    and bit 16 to set it; leaving bit 16 clear clears the selected mask.
    """
    command = VIBRATION_BIT_MASK | (0 if enabled else 0x10000)
    return command.to_bytes(4, "little")


def decode_vibration(data: bytes | bytearray) -> bool:
    return not bool(decode_uint(data) & VIBRATION_BIT_MASK)
