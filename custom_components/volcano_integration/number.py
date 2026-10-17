"""Writable numbers sharing the same state and validation as service actions."""

from dataclasses import dataclass

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory

from .const import (
    MAX_BRIGHTNESS,
    MAX_SHUTOFF_MINUTES,
    MAX_TEMP,
    MIN_BRIGHTNESS,
    MIN_SHUTOFF_MINUTES,
    MIN_TEMP,
)
from .entity import VolcanoEntity


@dataclass(frozen=True, kw_only=True)
class VolcanoNumberDescription(NumberEntityDescription):
    unique_key: str
    state_field: str
    setter: str


NUMBERS = (
    VolcanoNumberDescription(
        key="temperature",
        unique_key="heater_temperature_setpoint",
        state_field="target_temperature",
        setter="set_heater_temperature",
        name="Volcano Heater Temperature Setpoint",
        icon="mdi:thermometer",
        native_min_value=MIN_TEMP,
        native_max_value=MAX_TEMP,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
    ),
    VolcanoNumberDescription(
        key="brightness",
        unique_key="led_brightness_number",
        state_field="led_brightness",
        setter="set_led_brightness",
        name="Volcano LED Brightness (Writer)",
        icon="mdi:brightness-5",
        native_min_value=MIN_BRIGHTNESS,
        native_max_value=MAX_BRIGHTNESS,
        native_step=1,
        native_unit_of_measurement="%",
        entity_category=EntityCategory.CONFIG,
    ),
    VolcanoNumberDescription(
        key="shutoff",
        unique_key="auto_shutoff_minutes",
        state_field="auto_shut_off_setting",
        setter="set_auto_shutoff_setting",
        name="Volcano Auto Shutoff Setting",
        icon="mdi:timer-cog",
        native_min_value=MIN_SHUTOFF_MINUTES,
        native_max_value=MAX_SHUTOFF_MINUTES,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=NumberDeviceClass.DURATION,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    manager = entry.runtime_data
    async_add_entities(VolcanoNumber(manager, entry, description) for description in NUMBERS)


class VolcanoNumber(VolcanoEntity, NumberEntity):
    entity_description: VolcanoNumberDescription

    def __init__(self, manager, entry, description) -> None:
        super().__init__(manager, entry, description.unique_key)
        self.entity_description = description

    @property
    def native_value(self):
        return getattr(self.manager.state, self.entity_description.state_field)

    async def async_set_native_value(self, value: float) -> None:
        if self.entity_description.key == "temperature":
            unit = (
                self.manager.state.temperature_unit or self.manager.state.temperature_unit_fallback
            )
            if unit is None:
                raise HomeAssistantError(
                    "Volcano temperature unit is unknown; reconnect the device"
                )
            # HA passes native Celsius even when this entity is displayed in Fahrenheit.
            target = value * 9 / 5 + 32 if unit == "F" else value
            await self.manager.set_heater_temperature(target, unit=unit)
        else:
            await getattr(self.manager, self.entity_description.setter)(int(value))

    @property
    def extra_state_attributes(self):
        if self.entity_description.key == "temperature":
            return {
                "device_temperature_unit": self.manager.state.temperature_unit,
                "temperature_unit_fallback": self.manager.state.temperature_unit_fallback,
            }
        return None
