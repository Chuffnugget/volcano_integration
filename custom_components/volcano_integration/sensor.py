"""Read-only values using the existing sensor identities."""

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.helpers.entity import EntityCategory

from .const import BT_STATUS_CONNECTED, BT_STATUS_CONNECTING, BT_STATUS_DISCONNECTED
from .entity import VolcanoEntity


@dataclass(frozen=True, kw_only=True)
class VolcanoSensorDescription(SensorEntityDescription):
    unique_key: str
    state_field: str


SENSORS = (
    VolcanoSensorDescription(
        key="current_temperature",
        unique_key="current_temperature",
        state_field="current_temperature",
        name="Volcano Current Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    VolcanoSensorDescription(
        key="heat_status",
        unique_key="heat_status",
        state_field="heat_state",
        name="Volcano Heat Status",
        icon="mdi:fire",
    ),
    VolcanoSensorDescription(
        key="pump_status",
        unique_key="pump_status",
        state_field="pump_state",
        name="Volcano Pump Status",
        icon="mdi:air-purifier",
    ),
    VolcanoSensorDescription(
        key="bt_status",
        unique_key="bt_status",
        state_field="bt_status",
        name="Volcano Bluetooth Status",
        device_class=SensorDeviceClass.ENUM,
        options=[BT_STATUS_DISCONNECTED, BT_STATUS_CONNECTING, BT_STATUS_CONNECTED],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VolcanoSensorDescription(
        key="ble_firmware_version",
        unique_key="ble_firmware_version",
        state_field="ble_firmware_version",
        name="Volcano BLE Firmware Version",
        icon="mdi:information",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VolcanoSensorDescription(
        key="serial_number",
        unique_key="serial_number",
        state_field="serial_number",
        name="Volcano Serial Number",
        icon="mdi:card-account-details",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VolcanoSensorDescription(
        key="firmware_version",
        unique_key="firmware_version",
        state_field="firmware_version",
        name="Volcano Firmware Version",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VolcanoSensorDescription(
        key="led_brightness",
        unique_key="led_brightness",
        state_field="led_brightness",
        name="Volcano LED Brightness",
        icon="mdi:brightness-5",
        native_unit_of_measurement="%",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VolcanoSensorDescription(
        key="hours_of_operation",
        unique_key="hours_of_operation",
        state_field="hours_of_operation",
        name="Volcano Hours of Operation",
        icon="mdi:clock-outline",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VolcanoSensorDescription(
        key="minutes_of_operation",
        unique_key="minutes_of_operation",
        state_field="minutes_of_operation",
        name="Volcano Minutes of Operation",
        icon="mdi:clock-outline",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    manager = entry.runtime_data
    async_add_entities(VolcanoSensor(manager, entry, description) for description in SENSORS)


class VolcanoSensor(VolcanoEntity, SensorEntity):
    entity_description: VolcanoSensorDescription

    def __init__(self, manager, entry, description) -> None:
        super().__init__(manager, entry, description.unique_key)
        self.entity_description = description

    @property
    def native_value(self):
        value = getattr(self.manager.state, self.entity_description.state_field)
        if isinstance(value, bool):
            return "ON" if value else "OFF"
        return value

    @property
    def available(self) -> bool:
        return self.entity_description.key == "bt_status" or super().available

    @property
    def extra_state_attributes(self):
        if self.entity_description.key == "current_temperature":
            return {"device_temperature_unit": self.manager.state.temperature_unit}
        if self.entity_description.key == "bt_status":
            return {"connection_requested": self.manager.connection_requested}
        if self.entity_description.key in {"heat_status", "pump_status"}:
            return {"raw_status": self.manager.state.raw_status}
        return None
