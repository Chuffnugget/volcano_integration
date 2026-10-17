"""One immutable snapshot shared by services and entities."""

from dataclasses import dataclass

from .const import BT_STATUS_DISCONNECTED


@dataclass(frozen=True)
class VolcanoState:
    """Device readings and connection intent; None represents unknown data."""

    bt_status: str = BT_STATUS_DISCONNECTED
    connection_requested: bool = False
    current_temperature: float | None = None
    target_temperature: float | None = None
    temperature_unit: str | None = None
    heat_state: bool | None = None
    pump_state: bool | None = None
    raw_status: str | None = None
    ble_firmware_version: str | None = None
    serial_number: str | None = None
    firmware_version: str | None = None
    auto_shut_off_setting: int | None = None
    led_brightness: int | None = None
    hours_of_operation: int | None = None
    minutes_of_operation: int | None = None
    vibration: bool | None = None
