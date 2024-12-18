"""Sensors for Volcano Integration."""
from __future__ import annotations

import logging
import asyncio

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, UUID_TEMPERATURE
from .coordinator import GenericBTCoordinator
from .entity import GenericBTEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Sensors for Volcano Integration based on a config entry."""
    coordinator: GenericBTCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CurrentTemperatureSensor(coordinator)])

class CurrentTemperatureSensor(GenericBTEntity, SensorEntity):
    """Representation of the Current Temperature."""

    _attr_name = "Current Temperature"
    _attr_unit_of_measurement = "°C"
    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator: GenericBTCoordinator) -> None:
        """Initialize the temperature sensor."""
        super().__init__(coordinator)
        self._temperature = None
        self._update_task = asyncio.create_task(self._update_temperature())

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._temperature

    async def _update_temperature(self):
        """Fetch temperature every second."""
        while True:
            try:
                data = await self._device.read_gatt(UUID_TEMPERATURE)
                if data:
                    # Assuming temperature is a 2-byte little-endian integer
                    self._temperature = int.from_bytes(data[:2], byteorder='little') / 100  # Adjust as per device specs
                    self.async_write_ha_state()
            except Exception as e:
                _LOGGER.error("Error reading temperature: %s", e)
            await asyncio.sleep(1)  # Update every second

    async def async_will_remove_from_hass(self):
        """Cleanup when entity is removed."""
        self._update_task.cancel()
        await super().async_will_remove_from_hass()
