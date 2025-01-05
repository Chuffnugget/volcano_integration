"""Platform for number integration."""
import logging

from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfTime
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Volcano number entities for a config entry."""
    _LOGGER.debug("Setting up Volcano number entities for entry: %s", entry.entry_id)

    manager = hass.data[DOMAIN][entry.entry_id]

    entities = [
        VolcanoAutoShutOffSettingNumber(manager, entry),
        VolcanoLEDBrightnessNumber(manager, entry),
    ]
    async_add_entities(entities)


class VolcanoAutoShutOffSettingNumber(NumberEntity):
    """Number entity to set Auto Shutoff Duration."""

    def __init__(self, manager, config_entry):
        self._manager = manager
        self._config_entry = config_entry
        self._attr_name = "Volcano Auto Shutoff Setting"
        self._attr_unique_id = f"volcano_auto_shutoff_setting_{self._manager.bt_address}"
        self._attr_native_min_value = 1  # 1 minute
        self._attr_native_max_value = 1440  # 24 hours
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_icon = "mdi:timer-outline"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._manager.bt_address)},
            "name": self._config_entry.data.get("device_name", "Volcano Vaporizer"),
            "manufacturer": "Storz & Bickel",
            "model": "Volcano Hybrid Vaporizer",
            "sw_version": "1.0.0",
            "via_device": None,
        }

    @property
    def native_value(self):
        return self._manager.auto_shut_off_setting if self._manager.auto_shut_off_setting else 60

    @property
    def available(self):
        return (self._manager.bt_status == "CONNECTED")

    async def async_set_native_value(self, value: float) -> None:
        minutes = int(value)
        _LOGGER.debug("Setting Auto Shutoff Setting to %s minutes", minutes)
        await self._manager.set_auto_shutoff_setting(minutes)
        self.async_write_ha_state()


class VolcanoLEDBrightnessNumber(NumberEntity):
    """Number entity to set LED Brightness."""

    def __init__(self, manager, config_entry):
        self._manager = manager
        self._config_entry = config_entry
        self._attr_name = "Volcano LED Brightness"
        self._attr_unique_id = f"volcano_led_brightness_{self._manager.bt_address}"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "%"
        self._attr_icon = "mdi:brightness-5"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._manager.bt_address)},
            "name": self._config_entry.data.get("device_name", "Volcano Vaporizer"),
            "manufacturer": "Storz & Bickel",
            "model": "Volcano Hybrid Vaporizer",
            "sw_version": "1.0.0",
            "via_device": None,
        }

    @property
    def native_value(self):
        return self._manager.led_brightness if self._manager.led_brightness is not None else 50

    @property
    def available(self):
        return (self._manager.bt_status == "CONNECTED")

    async def async_set_native_value(self, value: float) -> None:
        brightness = int(value)
        _LOGGER.debug("Setting LED Brightness to %s%%", brightness)
        await self._manager.set_led_brightness(brightness)
        self.async_write_ha_state()
